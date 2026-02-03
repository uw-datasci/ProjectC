from argparse import ArgumentParser

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

def parse_args():
    parser = ArgumentParser()
    subparsers = parser.add_subparsers()
    prompt = subparsers.add_parser('prompt')
    category = subparsers.add_parser('category')
    prompt.add_argument('prompt', type=str,
                        help='Prompt to send to the agent')
    category.add_argument('category', type=str,
                        help='Category of prompts to use')
    category.add_argument('prompts_file', type=str,
                        help='JSON file containing prompts for category')
    return parser.parse_args()


def main():
    agent = create_agent(
        model='groq:qwen/qwen3-32b',
        system_prompt=SYSTEM_PROMPT,
        tools=[write_memory, get_memory],
        context_schema=Context,
    )
    harness = PromptHarness(agent, Context(user_id='1'))
    args = parse_args()
    if 'category' in args:
        harness.prompt_category(args.category, args.prompts_file)
        return
    elif 'prompt' in args:
        harness.prompt(args.prompt)
        return
    while True:
        try:
            inp = input('Enter prompt: ')
            if inp == '-c quit':
                break
            else:
                harness.prompt(inp)
        except EOFError, KeyboardInterrupt:
            print('\nThank you for chatting with our Therapy-LLM!')
            return

if __name__ == '__main__':
    main()