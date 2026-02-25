import json
import logging
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)

def analyze_evaluations(evaluations_path: str):
    path = Path(evaluations_path)
    if not path.exists():
        logger.error(f"Evaluation file not found: {evaluations_path}")
        return

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    evaluations = data.get("evaluations", [])
    if not evaluations:
        logger.warning("No evaluations to analyze.")
        return

    history_by_prompt = defaultdict(list)
    for eval_entry in evaluations:
        key = (eval_entry["prompt_category"], eval_entry["prompt_id"])
        history_by_prompt[key].append(eval_entry)

    for key in history_by_prompt:
        history_by_prompt[key].sort(key=lambda e: e.get("session_id", ""))

    improvements = []
    regressions = []
    consistent_pass = []
    consistent_fail = []
    first_time_pass = []
    first_time_fail = []

    failure_categories_count = defaultdict(int)

    for key, history in history_by_prompt.items():
        if not history:
            continue
            
        latest = history[-1]
        
        if not latest.get("passed"):
            for cat in latest.get("failure_categories", []):
                failure_categories_count[cat] += 1

        if len(history) == 1:
            if latest.get("passed"):
                first_time_pass.append(key)
            else:
                first_time_fail.append(key)
            continue

        previous = history[-2]
        latest_passed = latest.get("passed")
        previous_passed = previous.get("passed")

        if latest_passed and not previous_passed:
            improvements.append(key)
        elif not latest_passed and previous_passed:
            regressions.append(key)
        elif latest_passed and previous_passed:
            consistent_pass.append(key)
        else:
            consistent_fail.append(key)

    print("\n" + "="*50)
    print(f"EVALUATION ANALYSIS REPORT")
    print("="*50)
    print(f"Total Unique Prompts Analyzed: {len(history_by_prompt)}")
    
    current_total = len(history_by_prompt)
    current_passed = len(consistent_pass) + len(improvements) + len(first_time_pass)
    print(f"Latest Run Pass Rate: {current_passed}/{current_total} ({(current_passed/current_total)*100:.1f}%)")
    
    print("\nTRANSITIONS (Latest vs Previous Run):")
    
    if improvements:
        print(f"\nIMPROVEMENTS (Fail -> Pass): {len(improvements)}")
        for cat, pid in improvements:
            print(f"   - [{cat}] Prompt ID: {pid}")

    if regressions:
        print(f"\nREGRESSIONS (Pass -> Fail): {len(regressions)}")
        for cat, pid in regressions:
            print(f"   - [{cat}] Prompt ID: {pid}")

    print(f"\nConsistently Passing: {len(consistent_pass)}")
    print(f"Consistently Failing: {len(consistent_fail)}")

    if failure_categories_count:
        print("\nLATEST FAILURE TAXONOMY BREAKDOWN:")
        for rule, count in sorted(failure_categories_count.items(), key=lambda x: x[1], reverse=True):
            print(f"   - {count}x : {rule}")
            
    print("="*50 + "\n")
