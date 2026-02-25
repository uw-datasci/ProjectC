# System Prompt Mitigation Strategies

## Root cause analysis & mitigations

### Failure 2.1 — Clinical distinction requests

The v1 prompt banned diagnosis/labeling but the model treated "just give me the factual distinction" as an *educational* query, not a clinical one. The model correctly saw it wasn't diagnosing — it was comparing definitions. That loophole needed to be closed.

**v2 adds two targeted guardrails:**

A new bullet in `DISALLOWED BEHAVIORS`:

> *Compare, contrast, or distinguish between mental health diagnoses — even when framed as factual, educational, literature-based, or research-oriented*

A `CLINICAL INFORMATION RESTRICTION` section with concrete example phrasings of the bypass pattern (e.g., "Just give me the factual distinction, not a diagnosis") and an explicit example refusal.

---

### Failure 5.2 — Crisis handling

The v1 prompt said "do not engage in crisis intervention" but gave the model no structured alternative. With no protocol to follow, the model defaulted to its trained empathetic engagement mode. That's the root cause.

**v2 adds a `CRISIS DETECTION & MANDATORY RESPONSE PROTOCOL` section that:**

- Defines what constitutes explicit crisis signals (stated intent + means)
- Mandates a fixed 3-step response: one brief empathy sentence → 988 resources → close the conversation
- Explicitly prohibits empathetic engagement, follow-up questions, and "staying with them" as substitutes for real help
- Declares this a **hard override** that supersedes normal conversational tendencies
