from argparse import ArgumentParser

from langchain.agents import create_agent
from dotenv import load_dotenv

from agent import write_memory, get_memory, Context
from prompt import PromptHarness

load_dotenv()

def parse_args():
    parser = ArgumentParser()
    parser.add_argument('-s', '--system', type=str, default='system_prompt_v1.txt',
                        help='Location of the system prompt file')
    parser.add_argument('-m', '--model', type=str, default='groq:qwen/qwen3-32b',
                        help='Model to use')
    subparsers = parser.add_subparsers(dest='command')
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
    args = parse_args()
    with open(args.system) as f:
        SYSTEM_PROMPT = f.read()

    agent = create_agent(
        model=args.model,
        system_prompt=SYSTEM_PROMPT,
        tools=[write_memory, get_memory],
        context_schema=Context,
    )
    harness = PromptHarness(agent, Context(user_id='1'))
    if args.command == 'category':
        harness.prompt_category(args.category, args.prompts_file)
        return
    elif args.command == 'prompt':
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