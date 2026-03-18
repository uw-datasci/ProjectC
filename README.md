# Project C: Therapy-Style Conversational Agent 

Project C for UW x AI Tinkerers W26.

This project provides a test environment for studying prompt robustness, safety boundaries, and failure modes of a therapy-style conversational LLM. The agent is designed to provide neutral, reflective conversation while strictly preserving clinical and safety boundaries.

## Team Members
<table><tbody><tr>
<td align="center" valign="center" width="20%">
    Fouzan Abdullah
  </a>
</td>
<td align="center" valign="center" width="20%">
    Luna Nguyen
  </a>
</td>
<td align="center" valign="center" width="20%">
    Matthew Li
  </a>
</td>
<td align="center" valign="center" width="20%">
    Alia Cai
  </a>
</td>
<td align="center" valign="center" width="20%">
    Ruben Ispiryan
  </a>
</td>
</td></tr></tbody></table>
## Purpose

The agent is designed to **fail safely** rather than stretch capability. It prioritizes alignment and refusal correctness over user satisfaction.
It explicitly avoids providing medical or psychiatric advice, diagnosing conditions, or engaging in crisis intervention. 

## Features

- **Agent Framework**: Built using LangChain, featuring a memory system to maintain conversational state.
- **Evaluation Pipeline**: Evaluates agent responses using LLM-as-a-judge (Stage 1 and 2), checking compliance with safety outlines and classifying failure modes based on a strict taxonomy.
- **Dashboard**: Generates an interactive HTML dashboard to visualize pass rates, failure categories, latency, and model regressions over time.
- **Prompting Harness**: Provides tools to test single prompts or batch run categorized prompts (`benign`, `ambiguous`, `adversarial`).

## File Structure

- `src/`
  - `main.py`: The entry point for the application. Handles running prompts, evaluating, analyzing, and generating dashboards.
  - `agent.py`: LangChain-based agent implementation with memory tools.
  - `evaluator.py`: Implements `FailureEvaluator` for two-stage safety compliance evaluation.
  - `dashboard.py`: Generates the HTML visualization dashboard.
  - `analyze.py`: Processes evaluation results to compute metrics.
  - `model_pool.py`: Manages the pool of LLM models used for agency and evaluation.
- `data/`
  - `system_prompts/`: Contains versioned system prompts (`system_prompt_vX.txt`).
  - `test_prompts_v1.json`: Categorized test prompts.
  - `evaluation.json`: Output of the evaluation step.
  - `metrics.json`: Output of the analysis step.
  - `responses_combined.json`: Agent interaction responses.
- `agent_spec.md`: Detailed specification of the agent's safe behavior and failure boundaries.
- `failure_taxonomy.md`: Taxonomy of failure modes for the evaluator to classify.
- `requirements.txt`: Python dependencies.

## Setup & Installation

This project utilizes `uv` for package management and script execution, though standard `pip` can also be used.

1. Clone the repository and navigate to the project directory:
   ```bash
   cd ProjectC
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *Note: Using `uv pip install -r requirements.txt` is recommended for faster installation.*

3. Set up environment variables:
   Create a `.env` file in the root directory and add your API keys (e.g., `OPENAI_API_KEY`, `GROQ_API_KEY`, or others depending on `model_pool.py` config).

## Usage

The primary interface is `src/main.py`. You can run various commands to interact with the agent or run evaluations.

### 1. Chat/Test a Prompt
Send a single interactive prompt to the agent:
```bash
uv run src/main.py prompt "I'm feeling really stressed today."
```

### 2. Run a Category of Prompts
Run the agent against a specific category (`benign`, `ambiguous`, `adversarial`) from the test prompts file:
```bash
uv run src/main.py category benign data/test_prompts_v1.json
```
*(Use `all` as the category to run everything).*

### 3. Evaluate Responses
Run the evaluator on the generated responses to check for safety compliance:
```bash
uv run src/main.py evaluate --responses data/responses_combined.json --prompts data/test_prompts_v1.json --output data/evaluation.json
```

### 4. Analyze Results
Compute metrics from the evaluations:
```bash
uv run src/main.py analyze --evaluations data/evaluation.json --output data/metrics.json
```

### 5. Generate Dashboard
Create a visual HTML dashboard of the metrics:
```bash
uv run src/main.py dashboard --metrics data/metrics.json --output data/dashboard.html
```
