# Agentic Civic Engagement Framework — Developer README

> **Audience:** Sub-team B (Tool Wrappers), Sub-team C (Complaint Drafter), Sub-team D (Routing & Geo)  
> **Owner:** Sub-team A — Foundation  
> **Last updated:** 2024-11-14

---

## 1. What Changed and Why

The old `ComplaintContext` singleton in `app/context.py` is **deprecated**.  
It was a global mutable dict that made tools tightly coupled and untestable in isolation.

We have replaced it with:

| Old pattern | New pattern |
|---|---|
| `context.set("issue_category", val)` | Return a typed `ExtractedIssue` object |
| `context.get("authority_email")` | Receive an `AuthorityContact` object as input |
| Hard-coded pipeline in `main.py` | `smolagents` CodeAgent writes the pipeline at runtime |

**The agent reasons about which tools to call and in what order.**  
Your job is to write self-contained tools that the agent can compose.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    app/orchestrator.py                  │
│                                                         │
│   MediaMetadata ──► CodeAgent (LLM writes code) ──►    │
│                          │                             │
│         ┌────────────────┼────────────────┐            │
│         ▼                ▼                ▼            │
│   [vision_tool]  [geo_resolution]  [routing_tool]      │
│         │                │                │            │
│         └────────────────┴────────────────┘            │
│                          │                             │
│                   [assembly_tool]                      │
│                          │                             │
│                   FinalComplaint ◄─────────────────────┘
└─────────────────────────────────────────────────────────┘
```

The agent **passes JSON strings between tool calls**.  
Each tool parses its input from JSON and returns JSON. That's the entire contract.

---

## 3. The Four Core Schemas

All schemas live in `app/schemas/issue_schema.py`. Import from there — never redefine them locally.

### 3a. `MediaMetadata` — Pipeline Input
Describes the raw social-media post. **Created by the ingestion layer; you receive it read-only.**

Key fields your tools will read:
- `run_id` — UUID, must be echoed into every model you produce
- `media_url` — URL to the raw image/video
- `geotag` — raw location from the post (may be None)
- `caption` — post text (supplementary context for vision)

### 3b. `ExtractedIssue` — Vision Tool Output
Your vision tools (pair_b) **produce** this.  
Geo-resolution and routing tools (pair_d) **consume** it.

Key fields you must populate:
- `run_id` — copy from input `MediaMetadata.run_id`
- `category` — one of the `IssueCategory` enum values
- `severity` — one of `SeverityLevel`
- `description` — neutral factual text, suitable for an official document
- `confidence_score` — float 0.0–1.0; below 0.5 auto-flags for human review

### 3c. `AuthorityContact` — Routing Tool Output
Produced by pair_d routing tool; consumed by trio_c assembly tool.

### 3d. `FinalComplaint` — Terminal Output
Produced by trio_c assembly tool. The orchestrator returns this to callers.  
**Do not instantiate this in pair_b or pair_d tools.**

---

## 4. Tool Wrapping Guide

This is the exact pattern every tool in this project must follow.

### 4a. Minimal Skeleton

```python
# app/tools/pair_b/vision.py

import json
from smolagents import tool
from app.schemas.issue_schema import MediaMetadata, ExtractedIssue, IssueCategory, SeverityLevel

@tool
def vision_tool(media_metadata_json: str) -> str:
    """
    One-sentence summary of what this tool does.

    Longer explanation of the tool's behaviour, the model it calls, and any
    important edge cases.  smolagents uses this docstring to decide when and
    how to invoke this tool — write it for the LLM, not just for humans.

    Args:
        media_metadata_json: JSON string of a MediaMetadata object.
            Produced by MediaMetadata.model_dump_json().

    Returns:
        JSON string of an ExtractedIssue object.
        Callers should parse with ExtractedIssue.model_validate_json().
    """
    # 1. Deserialise the input
    media = MediaMetadata.model_validate_json(media_metadata_json)

    # 2. Run your existing logic
    raw_result = your_existing_vision_function(str(media.media_url), media.caption)

    # 3. Map the result into the schema
    issue = ExtractedIssue(
        run_id=media.run_id,          # Always echo run_id
        category=IssueCategory.SOLID_WASTE,
        severity=SeverityLevel.HIGH,
        description=raw_result["description"],
        detected_objects=raw_result["objects"],
        confidence_score=raw_result["confidence"],
        vision_model_id="your-model-id",
    )

    # 4. Return JSON
    return issue.model_dump_json()
```

### 4b. Rules You Must Follow

| Rule | Why |
|---|---|
| **Signature: `(str) -> str`** | smolagents CodeAgent only passes primitives between tool calls |
| **Parse input with `.model_validate_json()`** | Validates fields and gives you IDE autocomplete |
| **Echo `run_id` from input to output** | Enables end-to-end tracing and log correlation |
| **Return with `.model_dump_json()`** | Ensures consistent serialisation |
| **Docstring is mandatory** | The LLM reads it to decide how to call your tool |
| **Never import `app/context.py`** | It is deprecated; all state flows through function arguments |
| **Never raise bare `Exception`** | Wrap errors; return a JSON string with an `"error"` key if needed |

### 4c. Multi-Input Tools (trio_c Pattern)

Assembly tools take more than one input.  Each input is a separate `str` parameter:

```python
@tool
def complaint_assembly_tool(
    media_metadata_json: str,
    extracted_issue_json: str,
    authority_contact_json: str,
) -> str:
    """
    Merges all pipeline outputs into a FinalComplaint.

    Args:
        media_metadata_json: JSON string of MediaMetadata.
        extracted_issue_json: JSON string of a resolved ExtractedIssue
            (location_resolved must be populated).
        authority_contact_json: JSON string of AuthorityContact.

    Returns:
        JSON string of a FinalComplaint with status=VALIDATED.
    """
    media     = MediaMetadata.model_validate_json(media_metadata_json)
    issue     = ExtractedIssue.model_validate_json(extracted_issue_json)
    authority = AuthorityContact.model_validate_json(authority_contact_json)

    complaint = FinalComplaint(
        run_id=media.run_id,
        # ... map remaining fields
    )
    return complaint.model_dump_json()
```

---

## 5. Registering Your Tool

Open `app/orchestrator.py` and find `TOOL_REGISTRY`.  
Add your tool there — the agent will see it automatically.

```python
# app/orchestrator.py  (TOOL_REGISTRY section)

from app.tools.pair_b.vision import vision_tool          # ← pair_b adds this
from app.tools.pair_d.routing import routing_tool        # ← pair_d adds this
from app.tools.trio_c.assembly import assembly_tool      # ← trio_c adds this

TOOL_REGISTRY = [
    vision_tool,
    routing_tool,
    assembly_tool,
]
```

Once registered, remove the corresponding `dummy_*` tool from the list.

---

## 6. Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ORCHESTRATOR_LLM` | No | `hf` | `hf` for HF Inference API, `litellm` for any other provider |
| `HF_TOKEN` | If `ORCHESTRATOR_LLM=hf` | — | Hugging Face API token |
| `HF_MODEL_ID` | No | `Qwen/Qwen2.5-72B-Instruct` | HF model repo id |
| `LITELLM_MODEL` | If `ORCHESTRATOR_LLM=litellm` | `openai/gpt-4o` | LiteLLM model string |
| `LITELLM_API_KEY` | If `ORCHESTRATOR_LLM=litellm` | — | API key for the LiteLLM provider |

---

## 7. Running the Smoke Test

```bash
# Install dependencies
pip install smolagents pydantic

# With HF backend (free tier)
HF_TOKEN=hf_xxx python -m app.orchestrator

# With LiteLLM / OpenAI
ORCHESTRATOR_LLM=litellm LITELLM_MODEL=openai/gpt-4o LITELLM_API_KEY=sk-xxx \
    python -m app.orchestrator
```

Expected output: a pretty-printed `FinalComplaint` JSON with `status: "validated"`.

---

## 8. Testing Your Tool in Isolation

You do not need the full agent to test a single tool.  Call it like a normal Python function:

```python
# tests/pair_b/test_vision_tool.py

from app.schemas.issue_schema import MediaMetadata, MediaType
from app.tools.pair_b.vision import vision_tool
from datetime import datetime, timezone

def test_vision_tool_returns_valid_issue():
    media = MediaMetadata(
        media_url="https://example.com/img.jpg",
        media_type=MediaType.IMAGE,
        platform="twitter",
        posted_at=datetime(2024, 11, 1, tzinfo=timezone.utc),
    )

    result_json = vision_tool(media.model_dump_json())

    from app.schemas.issue_schema import ExtractedIssue
    issue = ExtractedIssue.model_validate_json(result_json)   # will raise if malformed

    assert issue.run_id == media.run_id
    assert 0.0 <= issue.confidence_score <= 1.0
```

---

## 9. FAQ

**Q: Can I add custom fields to the schemas?**  
A: No.  Request a schema change from Sub-team A.  Adding fields locally breaks other tools that re-validate the same JSON.

**Q: My tool needs to call an external API.  Where do I put credentials?**  
A: Use environment variables.  Never hard-code keys.  Read them inside your tool function with `os.getenv("MY_SERVICE_KEY")`.

**Q: The agent calls my tool with wrong arguments.  What do I do?**  
A: Improve your docstring. The agent's calling decision is driven entirely by the docstring — be explicit about what each argument is and what the return value contains.

**Q: Can my tool call another tool directly?**  
A: No.  Tools must be independent leaf functions.  The agent is responsible for orchestration.  Calling one tool from inside another bypasses the agent's reasoning and breaks composability.

**Q: What happens if `context.py` is imported in my code?**  
A: It will work for now but CI will emit a deprecation warning, and it will be removed before the v1.0 release.

---

## 10. Sub-team Ownership Map

| Sub-team | Directory | Input schema | Output schema |
|---|---|---|---|
| **A — Foundation** | `app/schemas/`, `app/orchestrator.py` | — | All schemas |
| **B — Vision** | `app/tools/pair_b/` | `MediaMetadata` | `ExtractedIssue` |
| **D — Routing & Geo** | `app/tools/pair_d/` | `ExtractedIssue` | `AuthorityContact` (+ updated `ExtractedIssue`) |
| **C — Complaint** | `app/tools/trio_c/` | `MediaMetadata` + `ExtractedIssue` + `AuthorityContact` | `FinalComplaint` |