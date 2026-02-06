from dataclasses import dataclass
import json
from pathlib import Path

from langchain.tools import ToolRuntime, tool

JSON_PATH = Path(__file__).parent.parent / 'data' / 'memory.json'


@dataclass
class Context:
    user_id: str


@tool
def write_memory(runtime: ToolRuntime[Context], memory_entry: tuple[str, str]):
    """Writes a memory entry (key, value) for the user to a json file."""
    with open(JSON_PATH, 'r') as f:
        current_memory = json.load(f)
        current_memory[runtime.context.user_id] = current_memory.get(
            runtime.context.user_id, {}
        )
        current_memory[runtime.context.user_id].update(
            {memory_entry[0]: memory_entry[1]}
        )
    with open(JSON_PATH, 'w') as f:
        json.dump(current_memory, f)


@tool
def get_memory(runtime: ToolRuntime[Context], memory_key: str) -> str:
    """Retrieves a memory entry for the user from a json file."""
    with open(JSON_PATH, 'r') as f:
        current_memory = json.load(f)
        return current_memory.get(runtime.context.user_id, {}).get(memory_key, '')