from langgraph.graph.state import CompiledStateGraph
from langchain.agents import create_agent
from dotenv import load_dotenv

from agent import write_memory, get_memory, Context
from prompt import PromptHarness

load_dotenv()

SYSTEM_PROMPT = """
Respond with only the final answer.
Do not include reasoning, thoughts, or <think> tags.

You have access to a memory store.
Whenever you learn stable, reusable, or user-specific information,
you should store it using the write_memory tool.
Do not store transient or speculative information.
"""



def main():
    agent = create_agent(
        model='groq:qwen/qwen3-32b',
        system_prompt=SYSTEM_PROMPT,
        tools=[write_memory, get_memory],
        context_schema=Context,
    )
    harness = PromptHarness(agent, Context(user_id='1'))
    while True:
        try:
            inp = input('Enter prompt:')
            if inp == '-c quit':
                break
            elif inp == '-c good':
                harness.prompt_category('good', 'src/prompts.json')
            elif inp == '-c adversarial':
                harness.prompt_category('adversarial', 'src/prompts.json')
            else:
                harness.prompt(inp)
        except EOFError, KeyboardInterrupt:
            print('\nThank you for chatting with our Therapy-LLM!')
            return
        response = harness.prompt(inp)

        ai_response = harness.extract_response_content(response)
        ai_response.pretty_print()

if __name__ == '__main__':
    main()