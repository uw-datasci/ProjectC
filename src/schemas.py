from dataclasses import field
from dataclasses import dataclass
from typing import ClassVar

@dataclass
class PromptSchema:
    id: int
    prompt: list[str]
    expected_behavior: str
    _counter: ClassVar[int] = 0

    def __post_init__(self):
        type(self)._counter += 1
        self.id = type(self)._counter


@dataclass
class PromptJSONSchema:
    benign: list[PromptSchema]
    ambiguous: list[PromptSchema]
    adversarial: list[PromptSchema]

@dataclass
class ResponseSchema:
    id: int = field(init=False)
    prompt_id: int
    prompt_category: str
    timestamp: str
    latency: float
    response: str
    _counter: ClassVar[int] = 0

    def __post_init__(self):
        type(self)._counter += 1
        self.id = type(self)._counter


@dataclass
class ResponseMetadata:
    session_id: int
    start_time: str
    prompts_sent: int
    errors: int
    model_name: str

    
@dataclass
class ResponseJSONSchema:
    responses: list[ResponseSchema]
    metadata: ResponseMetadata
