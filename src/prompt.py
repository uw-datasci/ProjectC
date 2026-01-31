import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any

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

class PromptHarness:
    def __init__(self, agent: CompiledStateGraph, ctx: Context, max_retries: int = 3):
        self.agent = agent
        self.ctx = ctx
        self.max_retries = max_retries
        self.history = []
        self.metadata = {
            'session_id': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'start_time': datetime.now().isoformat(),
            'prompts_sent': 0,
            'errors': 0
        }
        logger.info(f'PromptHarness initialized with session_id: {self.metadata['session_id']}') 

    def prompt(self, inp: str) -> Optional[Dict[Any, Any]]:
        self.metadata['prompts_sent'] += 1
        logger.info(f'Prompt #{self.metadata['prompts_sent']}: {inp}')
        
        self.history.append(inp)
        
        for attempt in range(self.max_retries):
            start_time = time.time()
            response = self.agent.invoke(
                {'messages': self.history},
                context=self.ctx
            )
            latency = time.time() - start_time
            
            if response and 'messages' in response:
                self.history = response['messages']
                
            logger.info(f'Response received (latency: {latency:.2f}s)')
            logger.info(f'Response #{self.metadata['prompts_sent']}: {self.extract_response_content(response)}')
            logger.debug(f'Response content: {response}')
            return response
                
        return None 

    def extract_response_content(self, response: dict):
        return response['messages'][-1].content

    def prompt_category(self, category: str, file_name: str):
        logger.info(f'Starting category: {category} from {file_name}')
        
        try:
            with open(file_name, 'r') as f:
                prompt_file = json.load(f)
                prompts = prompt_file[category]
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
        for i, prompt in enumerate(prompts, 1):
            logger.info(f'Processing prompt {i}/{len(prompts)} in category "{category}"')
            response = self.prompt(prompt)
            responses.append(response)
        
        logger.info(f'Category "{category}" completed: {len(responses)} responses')
        return responses
    
    def get_metadata(self) -> Dict[str, Any]:
        self.metadata['end_time'] = datetime.now().isoformat()
        return self.metadata.copy()
