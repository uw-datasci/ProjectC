from argparse import ArgumentError
from dataclasses import asdict
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from schemas import ResponseSchema, PromptSchema, PromptJSONSchema, \
 ResponseJSONSchema, ResponseMetadata

from contextvars import Context
from langgraph.graph.state import CompiledStateGraph
from model_pool import ModelPool

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/experiment.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

RESPONSES_DIR = Path(__file__).parent.parent / 'data' / 'responses'

class PromptHarness:
    def __init__(self, agent: CompiledStateGraph, ctx: Context, model_name: str,
                author: str, pool: ModelPool | None = None,
                agent_factory: Callable[[str], CompiledStateGraph] | None = None,
                max_retries: int = 3, keep_history: bool = True):
        self.agent = agent
        self.ctx = ctx
        self.pool = pool
        self.agent_factory = agent_factory
        self.max_retries = max_retries
        self.history = []
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.metadata = ResponseMetadata(
            session_id=session_id,
            author=author,
            start_time=datetime.now().isoformat(),
            prompts_sent=0,
            errors=0,
            model_name=model_name
        )
        self.keep_history = keep_history
        response_path = RESPONSES_DIR / f'{author}_{session_id}.json'
        self.response_logger = ResponseJSONLogger(response_path, self.metadata)
        logger.info(f'PromptHarness initialized with session_id: {session_id}, author: {author}') 

    def _rotate_agent(self):
        if self.pool and self.agent_factory:
            new_model = self.pool.rotate()
            logger.info(f'Recreating agent with model: {new_model}')
            self.agent = self.agent_factory(new_model)
            self.metadata.model_name = new_model
            return True
        return False

    def prompt(self, inp: str | PromptSchema, category: str | None) -> Optional[Dict[Any, Any]]:
        if isinstance(inp, str):
            prompt_texts = [inp]
        elif isinstance(inp, PromptSchema):
            prompt_texts = inp.prompt
        else:
            raise TypeError('Invalid input type: ', type(inp))
        response = None
        for prompt_text in prompt_texts:
            self.metadata.prompts_sent += 1
            logger.info(f'Prompt #{self.metadata.prompts_sent}: {prompt_text}')
        
            if not self.keep_history:
                self.history.clear()
            self.keep_history = len(prompt_texts) > 1
            logger.info(f'History saving is set to: {self.keep_history}')
            self.history.append(prompt_text)
        
            attempts_left = self.max_retries * max(1, len(self.pool.model_names) if self.pool else 1)
            while attempts_left > 0:
                attempts_left -= 1
                start_time = time.time()
                try:
                    response = self.agent.invoke(
                        {'messages': self.history},
                        context=self.ctx
                    )
                except Exception as e:
                    error_str = str(e)
                    is_rate_limit = any(code in error_str.lower() for code in ['429', '413', 'rate_limit', 'too many requests'])
                    if is_rate_limit and self._rotate_agent():
                        logger.warning(f'Rate limited, retrying with {self.pool.current}...')
                        continue
                    raise

                if response is None:
                    self.metadata.errors += 1
                    logger.error('No response received')
                    continue
                response_time = datetime.now()
                latency = time.time() - start_time
            
                if response and 'messages' in response:
                    self.history = response['messages']
                
                logger.info(f'Response received (latency: {latency:.2f}s)')
                logger.info(f'Response #{self.metadata.prompts_sent}: {self.extract_response_content(response)}')
                logger.debug(f'Response content: {response}')
                if isinstance(inp, PromptSchema):
                    self.response_logger.log_response(ResponseSchema(
                        prompt_id=inp.id,
                        prompt_category=category,
                        timestamp=str(response_time),
                        latency=latency,
                        response=self.extract_response_content(response).encode('utf-8').decode('utf-8'),
                    ))
                break
        return response 

    def extract_response_content(self, response: dict):
        if 'messages' not in response or not response['messages'] or \
            len(response['messages']) == 0:
            logger.error('No messages in response')
            logger.debug(f'Response: {response}')
            raise ValueError('No messages in response')
        return response['messages'][-1].content

    def prompt_category(self, category: str, file_name: str, prompt_ids: list[int] | None = None):
        logger.info(f'Starting category: {category} from {file_name}')
        
        try:
            with open(file_name, 'r', encoding='utf-8') as f:
                prompt_json_schema = PromptJSONSchema(**json.load(f))
                prompts = list(map(lambda x: PromptSchema(**x), getattr(prompt_json_schema, category)))
        except FileNotFoundError:
            logger.error(f'Prompt file not found: {file_name}')
            return []
        except json.JSONDecodeError as e:
            logger.error(f'Invalid JSON in {file_name}: {str(e)}')
            return []
        except KeyError:
            logger.error(f'Category "{category}" not found in {file_name}')
            return []

        if prompt_ids:
            prompts = [p for p in prompts if p.id in prompt_ids]
            logger.info(f'Filtered to {len(prompts)} prompt(s) with IDs: {prompt_ids}')

        responses = []
        for i, prompt_obj in enumerate(prompts, 1):
            logger.info(f'Processing prompt {i}/{len(prompts)} in category "{category}"')
            try:
                response = self.prompt(prompt_obj, category)
                responses.append(response)
            except Exception as e:
                self.metadata.errors += 1
                logger.error(f'Prompt {i}/{len(prompts)} failed: {type(e).__name__}: {e}')
                logger.info(f'Saved {len(responses)} responses so far, continuing...')
            if i < len(prompts):
                time.sleep(3)
        
        logger.info(f'Category "{category}" completed: {len(responses)}/{len(prompts)} responses')
        return responses
    
    def get_metadata(self) -> Dict[str, Any]:
        self.metadata.end_time = datetime.now().isoformat()
        return self.metadata.copy()


class ResponseJSONLogger:
    def __init__(self, file_name: Path, metadata: ResponseMetadata):
        self.file_name = file_name
        self.metadata = metadata
        self._init_response_json()

    def _init_response_json(self):
        self.file_name.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_name, 'w', encoding='utf-8') as f:
            json.dump(ResponseJSONSchema([], self.metadata), f,
                      indent=2, default=asdict, ensure_ascii=False)

    def log_response(self, response: ResponseSchema):
        with open(self.file_name, 'r', encoding='utf-8') as f:
            response_json = ResponseJSONSchema(**json.load(f))
        response_json.responses.append(response)
        with open(self.file_name, 'w', encoding='utf-8') as f:
            json.dump(response_json, f, indent=2, default=asdict, ensure_ascii=False)

    def log_responses(self, responses: list[ResponseSchema]):
        for response in responses:
            self.log_response(response)


def merge_responses(output_path: str = 'data/responses_combined.json') -> dict:
    output = Path(output_path)

    existing_runs: dict[str, dict] = {}
    existing_responses: list[dict] = []
    if output.exists():
        with open(output, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        existing_responses = existing.get('responses', [])
        for run in existing.get('runs', []):
            existing_runs[run['session_id']] = run

    seen = {(r['session_id'], r['prompt_id']) for r in existing_responses}

    new_responses = []
    run_files = sorted(RESPONSES_DIR.glob('*.json'))

    if not run_files:
        logger.warning(f'No response files found in {RESPONSES_DIR}')
        return {'responses': existing_responses, 'runs': list(existing_runs.values())}

    for run_file in run_files:
        with open(run_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        metadata = data.get('metadata', {})
        session_id = metadata.get('session_id', run_file.stem)

        if session_id not in existing_runs:
            existing_runs[session_id] = metadata

        for resp in data.get('responses', []):
            key = (session_id, resp.get('prompt_id'))
            if key not in seen:
                resp['session_id'] = session_id
                new_responses.append(resp)
                seen.add(key)

    all_responses = existing_responses + new_responses
    combined = {
        'responses': all_responses,
        'runs': list(existing_runs.values()),
    }

    with open(output, 'w', encoding='utf-8') as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    logger.info(f'Merged {len(run_files)} run(s): '
                f'{len(new_responses)} new + {len(existing_responses)} existing '
                f'= {len(all_responses)} total responses → {output}')
    return combined
        