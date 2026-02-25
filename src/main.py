from argparse import ArgumentParser
import os
import glob
import re

from langchain.agents import create_agent
from dotenv import load_dotenv

from agent import write_memory, get_memory, Context
from prompt import PromptHarness, merge_responses
from evaluator import FailureEvaluator
from model_pool import ModelPool, AGENT_MODELS, EVALUATOR_MODELS

load_dotenv()

def get_latest_system_prompt(prompts_dir='data/system_prompts'):
    files = glob.glob(os.path.join(prompts_dir, 'system_prompt_v*.txt'))
    if not files:
        return os.path.join(prompts_dir, 'system_prompt_v1.txt')
    
    def get_version(f):
        m = re.search(r'system_prompt_v(\d+)\.txt$', f)
        return int(m.group(1)) if m else -1
        
    return max(files, key=get_version)

def parse_args():
    parser = ArgumentParser()
    parser.add_argument('-s', '--system', type=str, default=get_latest_system_prompt(),
                        help='Location of the system prompt file')
    subparsers = parser.add_subparsers(dest='command')
    prompt = subparsers.add_parser('prompt')
    category = subparsers.add_parser('category')
    prompt.add_argument('prompt', type=str,
                        help='Prompt to send to the agent')
    category.add_argument('category', type=str,
                        help='Category of prompts to use')
    category.add_argument('prompts_file', type=str,
                        help='JSON file containing prompts for category')
    category.add_argument('--ids', type=int, nargs='+', default=None,
                        help='Only run specific prompt IDs (e.g. --ids 3 7 11)')

    merge = subparsers.add_parser('merge')
    merge.add_argument('--output', type=str, default='data/responses_combined.json',
                       help='Path to write the combined responses file')

    evaluate = subparsers.add_parser('evaluate')
    evaluate.add_argument('--responses', type=str, default='data/responses_combined.json',
                          help='Path to responses JSON file')
    evaluate.add_argument('--prompts', type=str, default='data/test_prompts_v1.json',
                          help='Path to test prompts JSON file')
    evaluate.add_argument('--taxonomy', type=str, default='failure_taxonomy.md',
                          help='Path to failure taxonomy markdown file')
    evaluate.add_argument('--output', type=str, default='data/evaluation.json',
                          help='Path to write evaluation report')
    return parser.parse_args()


def main():
    args = parse_args()

    if args.command == 'merge':
        combined = merge_responses(args.output)
        print(f"Merged {len(combined['responses'])} responses from {len(combined['runs'])} run(s)")
        return

    if args.command == 'evaluate':
        evaluator = FailureEvaluator(
            models=EVALUATOR_MODELS,
            taxonomy_path=args.taxonomy,
            prompts_path=args.prompts,
            temperature=0,
        )
        report = evaluator.evaluate_responses(args.responses, args.output)
        meta = report.metadata
        run = meta.get('run_history', [{}])[-1] if meta.get('run_history') else {}
        print(f"\nThis run:  {run.get('passed', 0)}/{run.get('total', 0)} passed")
        print(f"Total:     {meta.get('passed', 0)}/{meta.get('total', 0)} passed")
        return

    with open(args.system) as f:
        SYSTEM_PROMPT = f.read()

    pool = ModelPool(AGENT_MODELS)

    def make_agent(model: str):
        llm = pool.get_llm(model)
        return create_agent(
            model=llm,
            system_prompt=SYSTEM_PROMPT,
            tools=[write_memory, get_memory],
            context_schema=Context,
        )

    agent = make_agent(pool.current)
    author = os.environ.get('AUTHOR', 'unknown')
    harness = PromptHarness(
        agent, Context(user_id='1'),
        model_name=pool.current,
        author=author,
        pool=pool,
        agent_factory=make_agent,
    )
    if args.command == 'category':
        harness.prompt_category(args.category, args.prompts_file, prompt_ids=args.ids)
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
        except (EOFError, KeyboardInterrupt):
            print('\nThank you for chatting with our Therapy-LLM!')
            return

if __name__ == '__main__':
    main()