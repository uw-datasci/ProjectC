import logging
import time
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model

load_dotenv()

logger = logging.getLogger(__name__)

AGENT_MODELS = [
    'groq:qwen/qwen3-32b',
    'groq:llama-3.3-70b-versatile',
    'groq:meta-llama/llama-4-maverick-17b-128e-instruct',
    'groq:meta-llama/llama-4-scout-17b-16e-instruct',
    'groq:openai/gpt-oss-120b',
    'groq:openai/gpt-oss-20b',
    'groq:moonshotai/kimi-k2-instruct-0905',
    'groq:llama-3.1-8b-instant',
    'groq:openai/gpt-oss-safeguard-20b',
]

EVALUATOR_MODELS = [
    'groq:llama-3.3-70b-versatile',
    'groq:meta-llama/llama-4-maverick-17b-128e-instruct',
    'groq:openai/gpt-oss-120b',
    'groq:meta-llama/llama-4-scout-17b-16e-instruct',
    'groq:moonshotai/kimi-k2-instruct-0905',
    'groq:openai/gpt-oss-20b',
    'groq:qwen/qwen3-32b',
    'groq:llama-3.1-8b-instant',
    'groq:openai/gpt-oss-safeguard-20b',
]

CHECKER_MODELS = [
    'groq:meta-llama/llama-4-scout-17b-16e-instruct',
    'groq:llama-3.1-8b-instant',
    'groq:openai/gpt-oss-safeguard-20b',
    'groq:moonshotai/kimi-k2-instruct-0905',
    'groq:llama-3.3-70b-versatile',
    'groq:openai/gpt-oss-20b',
    'groq:qwen/qwen3-32b',
    'groq:meta-llama/llama-4-maverick-17b-128e-instruct',
    'groq:openai/gpt-oss-120b',
]


class ModelPool:
    def __init__(self, models: list[str], **kwargs):
        self.model_names = models
        self.kwargs = kwargs
        self.index = 0
        self._llms: dict[int, object] = {}

    @property
    def current(self) -> str:
        return self.model_names[self.index]

    def get_llm(self, model_name: str):
        import os
        if model_name not in self._llms:
            logger.info(f'Initializing model: {model_name}')
            api_key = os.environ.get('GROQ_API_KEY')
            if api_key:
                self._llms[model_name] = init_chat_model(model_name, api_key=api_key, max_retries=0, **self.kwargs)
            else:
                self._llms[model_name] = init_chat_model(model_name, max_retries=0, **self.kwargs)
        return self._llms[model_name]

    def rotate(self) -> str:
        self.index = (self.index + 1) % len(self.model_names)
        logger.info(f'Rotated to model: {self.current}')
        return self.current

    def invoke(self, messages):
        start_index = self.index
        while True:
            llm = self.get_llm(self.current)
            try:
                return llm.invoke(messages)
            except Exception as e:
                error_str = str(e)
                is_rate_limit = any(code in error_str for code in ['429', '413', 'rate_limit', 'Too Many Requests'])
                if not is_rate_limit:
                    raise

                logger.warning(f'Rate limited on {self.current}: {error_str[:120]}')
                self.rotate()

                if self.index == start_index:
                    logger.error('All models rate limited, waiting 60s before retrying...')
                    time.sleep(60)
                    return self.invoke(messages)
