from argparse import ArgumentError
from dataclasses import asdict
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from schemas import ResponseSchema, PromptSchema, PromptJSONSchema, \
 ResponseJSONSchema, ResponseMetadata

from contextvars import Context
from langgraph.graph.state import CompiledStateGraph

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('experiment.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

RESPONSE_JSON_PATH = Path(__file__).parent.parent / 'data' / 'responses.json'

class PromptHarness:
    def __init__(self, agent: CompiledStateGraph, ctx: Context, model_name: str,
                max_retries: int = 3, keep_history: bool = True):
        self.agent = agent
        self.ctx = ctx
        self.max_retries = max_retries
        self.history = []
        self.metadata = ResponseMetadata(
            session_id=datetime.now().strftime('%Y%m%d_%H%M%S'),
            start_time=datetime.now().isoformat(),
            prompts_sent=0,
            errors=0,
            model_name=model_name
        )
        self.keep_history = keep_history
        self.response_logger = ResponseJSONLogger(RESPONSE_JSON_PATH, self.metadata)
        logger.info(f'PromptHarness initialized with session_id: {self.metadata.session_id}') 

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
            logger.info(f'History saving is set to: {self.keep_history}')
            self.history.append(prompt_text)
        
            for attempt in range(self.max_retries):
                start_time = time.time()
                response = self.agent.invoke(
                    {'messages': self.history},
                    context=self.ctx
                )
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

    def prompt_category(self, category: str, file_name: str):
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
        
        responses = []
        for i, prompt_obj in enumerate(prompts, 1):
            logger.info(f'Processing prompt {i}/{len(prompts)} in category "{category}"')
            response = self.prompt(prompt_obj, category)
            responses.append(response)
        
        logger.info(f'Category "{category}" completed: {len(responses)} responses')
        return responses
    
    def get_metadata(self) -> Dict[str, Any]:
        self.metadata.end_time = datetime.now().isoformat()
        return self.metadata.copy()


class ResponseJSONLogger:
    def __init__(self, file_name: str, metadata: ResponseMetadata):
        self.file_name = file_name
        self.metadata = metadata
        self._init_response_json()

    def _init_response_json(self):
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
        