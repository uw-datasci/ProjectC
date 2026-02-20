import json
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

evaluation_path = os.path.join(BASE_DIR, "evaluation.json")
responses_path = os.path.join(BASE_DIR, "responses_combined.json")
prompts_path = os.path.join(BASE_DIR, "test_prompts_v1.json")
memory_path = os.path.join(BASE_DIR, "memory.json")

load_dotenv()

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
WORKSHEET_NAME = "Sheet1"


with open(evaluation_path) as f:
    evaluation_data = json.load(f)

with open(responses_path) as f:
    responses_data = json.load(f)

with open(prompts_path) as f:
    prompts_data = json.load(f)

with open(memory_path) as f:
    memory_data = json.load(f)


# --- Build lookup tables ---

# prompt_id -> prompt_text
prompt_lookup = {}
for category, prompts in prompts_data.items():
    for item in prompts:
        prompt_lookup[(category, item["id"])] = item["prompt"][0]

# (category, response_id, session_id) -> {response, latency}
response_lookup = {}
for item in responses_data["responses"]:
    key = (item["prompt_category"], item["id"], item["session_id"])
    response_lookup[key] = {
        "response": item["response"],
        "latency": item.get("latency", ""),
    }

# session_id -> model_name (main model used for that run)
run_lookup = {}
for run in responses_data.get("runs", []):
    run_lookup[run["session_id"]] = run.get("model_name", "")

# eval model from metadata (same for all rows)
eval_model = evaluation_data.get("metadata", {}).get("evaluator_model", "")

# --- Build rows ---

rows = []

for entry in evaluation_data["evaluations"]:

    if entry.get("passed", True):
        continue

    category = entry["prompt_category"]
    prompt_id = entry["prompt_id"]
    response_id = entry["response_id"]
    session_id = entry["session_id"]

    prompt_text = prompt_lookup.get((category, prompt_id), "")

    resp_info = response_lookup.get((category, response_id, session_id), {})
    response_text = resp_info.get("response", "")
    latency = resp_info.get("latency", "")

    failure_cats = entry.get("failure_categories", [])
    if failure_cats:
        error_type = ", ".join(failure_cats)
    elif entry.get("severity"):
        error_type = entry["severity"]
    else:
        error_type = "Unspecified"

    row = {
        "session_id": session_id,
        "response_id": response_id,
        "prompt_id": prompt_id,
        "prompt_category": category,
        "prompt_text": prompt_text,
        "response_text": response_text,
        "reasoning_text": entry.get("reasoning", ""),
        "error_type": error_type,
        "main_model": run_lookup.get(session_id, ""),
        "eval_model": eval_model,
        "latency": latency,
        "system_prompt_v": "",
    }

    rows.append(row)

df = pd.DataFrame(rows)


scopes = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=scopes
)

client = gspread.authorize(credentials)

sheet = client.open_by_key(SPREADSHEET_ID)
worksheet = sheet.worksheet(WORKSHEET_NAME)

worksheet.clear()

worksheet.update(
    [df.columns.values.tolist()] + df.values.tolist()
)

print("Sheet updated successfully.")