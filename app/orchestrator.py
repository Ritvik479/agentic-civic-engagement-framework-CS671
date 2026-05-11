"""
app/orchestrator.py

smolagents CodeAgent orchestrator for the Agentic Civic Engagement Framework.
This module is the single entry-point for all complaint-processing runs.

Execution flow (high-level):
  1.  Caller supplies a MediaMetadata object.
  2.  The CodeAgent receives a natural-language task prompt containing the
      serialised metadata.
  3.  The agent writes and executes Python code, calling registered @tool
      functions in the correct order.
  4.  A FinalComplaint object is returned (or an error state if any tool fails).

Developer notes:
  - Drop new tools into `app/tools/<your_pair>/` and register them in
    TOOL_REGISTRY below.  The agent will discover them automatically.
  - Never import context.py in new code.  All shared state travels through
    Pydantic model instances passed between tools.
  - Set HF_TOKEN (and optionally LITELLM_API_KEY) in your environment before
    running.  See the README for details.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# smolagents imports
# ---------------------------------------------------------------------------
from smolagents import CodeAgent, HfApiModel, LiteLLMModel, tool
from smolagents.models import MessageRole

# ---------------------------------------------------------------------------
# Schema imports
# ---------------------------------------------------------------------------
from app.schemas.issue_schema import (
    AuthorityContact,
    ComplaintStatus,
    ExtractedIssue,
    FinalComplaint,
    IssueCategory,
    MediaMetadata,
    MediaType,
    SeverityLevel,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("orchestrator")


# ===========================================================================
# SECTION 1 — LLM FACTORY
# ===========================================================================
# Toggle between HfApiModel (free / HF Inference API) and LiteLLMModel
# (OpenAI, Anthropic, Gemini, etc.) via the ORCHESTRATOR_LLM env var.

def _build_llm() -> HfApiModel | LiteLLMModel:
    """
    Returns the configured LLM backend.

    Environment variables
    ─────────────────────
    ORCHESTRATOR_LLM   : "hf" (default) | "litellm"
    HF_TOKEN           : Required when ORCHESTRATOR_LLM=hf
    HF_MODEL_ID        : HF model repo id (default: Qwen/Qwen2.5-72B-Instruct)
    LITELLM_MODEL      : LiteLLM model string (e.g. "openai/gpt-4o")
    LITELLM_API_KEY    : API key forwarded to LiteLLM
    """
    backend = os.getenv("ORCHESTRATOR_LLM", "hf").lower()

    if backend == "litellm":
        model_id = os.getenv("LITELLM_MODEL", "openai/gpt-4o")
        api_key  = os.getenv("LITELLM_API_KEY")
        logger.info("LLM backend: LiteLLMModel  model=%s", model_id)
        return LiteLLMModel(model_id=model_id, api_key=api_key)

    # Default: HF Inference API
    model_id = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-72B-Instruct")
    token    = os.getenv("HF_TOKEN")
    logger.info("LLM backend: HfApiModel  model=%s", model_id)
    return HfApiModel(model_id=model_id, token=token)


# ===========================================================================
# SECTION 2 — TOOL DEFINITIONS
# ===========================================================================
# Each @tool function must:
#   (a) Accept only JSON-serialisable primitive types OR a JSON *string*
#       representation of a Pydantic model (smolagents constraint).
#   (b) Return a JSON string so the CodeAgent can parse/pass it onwards.
#   (c) Include a thorough docstring — smolagents uses it to decide WHEN and
#       HOW to call the tool.
#
# See the Tool Wrapping Guide in DEVELOPER_README.md for the full pattern.


# ---------------------------------------------------------------------------
# 2a — DUMMY TOOL (reference implementation for Sub-team B / C / D)
# ---------------------------------------------------------------------------

@tool
def dummy_vision_tool(media_metadata_json: str) -> str:
    """
    DUMMY / REFERENCE IMPLEMENTATION — replace with the real vision tool.

    Accepts a serialised MediaMetadata object, pretends to run a vision model,
    and returns a serialised ExtractedIssue.

    This tool exists solely so:
      1. The agent skeleton is runnable end-to-end out of the box.
      2. Sub-team B has a concrete example of the expected tool signature.

    Args:
        media_metadata_json: JSON string produced by MediaMetadata.model_dump_json().
            Must contain at minimum the fields `run_id`, `media_url`, and `media_type`.

    Returns:
        JSON string of an ExtractedIssue object ready for model_validate_json().
    """
    data     = json.loads(media_metadata_json)
    run_id   = data["run_id"]

    # In production this block would call a vision model API.
    # Here we return plausible hard-coded values so the pipeline can run.
    issue = ExtractedIssue(
        run_id=run_id,
        category=IssueCategory.SOLID_WASTE,
        severity=SeverityLevel.HIGH,
        location_raw="Near Railway Station Rd, Sector 12",
        location_resolved=None,          # geo-resolution tool fills this later
        description=(
            "Large accumulation of mixed solid waste visible on the roadside. "
            "Includes plastic bags, construction debris, and organic matter. "
            "Potential vector breeding site."
        ),
        detected_objects=["plastic bags", "construction debris", "organic waste"],
        confidence_score=0.91,
        vision_model_id="dummy-v0",
    )

    logger.info("[dummy_vision_tool] ExtractedIssue built  run_id=%s", run_id)
    return issue.model_dump_json()


@tool
def dummy_geo_resolution_tool(extracted_issue_json: str) -> str:
    """
    DUMMY / REFERENCE IMPLEMENTATION — replace with the real geo-resolution tool.

    Accepts a serialised ExtractedIssue, resolves `location_raw` to a
    standardised address string, and returns the updated ExtractedIssue.

    Args:
        extracted_issue_json: JSON string of an ExtractedIssue.
            The `location_raw` field is used as the geocoding query.

    Returns:
        JSON string of the updated ExtractedIssue with `location_resolved` populated.
    """
    issue_data = json.loads(extracted_issue_json)
    # Real implementation: call Google Maps / Nominatim / govt GIS API here.
    issue_data["location_resolved"] = "Sector 12, Dwarka, New Delhi — 110078"

    # Re-validate through the schema to catch any field drift.
    updated_issue = ExtractedIssue.model_validate(issue_data)
    logger.info(
        "[dummy_geo_resolution_tool] Location resolved  run_id=%s  → %s",
        issue_data["run_id"],
        updated_issue.location_resolved,
    )
    return updated_issue.model_dump_json()


@tool
def dummy_authority_routing_tool(extracted_issue_json: str) -> str:
    """
    DUMMY / REFERENCE IMPLEMENTATION — replace with the real routing tool.

    Looks up the correct government authority for a detected issue category
    and jurisdiction, and returns an AuthorityContact.

    Args:
        extracted_issue_json: JSON string of an ExtractedIssue.
            Uses `category` and `location_resolved` to query the authority database.

    Returns:
        JSON string of an AuthorityContact object.
    """
    issue = ExtractedIssue.model_validate_json(extracted_issue_json)

    # Real implementation: query a database / government API here.
    contact = AuthorityContact(
        run_id=issue.run_id,
        department_name="South Delhi Municipal Corporation — Solid Waste Management",
        department_code="SDMC-SWM",
        submission_email="swm.complaints@sdmc.delhi.gov.in",
        submission_api_url=None,          # not yet available in staging
        portal_url="https://mcdonline.nic.in/portal",
        jurisdiction="South Delhi Municipal Zone",
        escalation_authority="Delhi Pollution Control Committee",
        sla_days=21,
    )

    logger.info(
        "[dummy_authority_routing_tool] Authority resolved  run_id=%s  → %s",
        issue.run_id,
        contact.department_code,
    )
    return contact.model_dump_json()


@tool
def dummy_complaint_assembly_tool(
    media_metadata_json: str,
    extracted_issue_json: str,
    authority_contact_json: str,
) -> str:
    """
    DUMMY / REFERENCE IMPLEMENTATION — replace with the real complaint assembly tool.

    Merges MediaMetadata, ExtractedIssue, and AuthorityContact into a
    submission-ready FinalComplaint.

    Args:
        media_metadata_json: JSON string of the original MediaMetadata.
        extracted_issue_json: JSON string of the resolved ExtractedIssue.
        authority_contact_json: JSON string of the AuthorityContact.

    Returns:
        JSON string of a FinalComplaint with status=VALIDATED.
    """
    media     = MediaMetadata.model_validate_json(media_metadata_json)
    issue     = ExtractedIssue.model_validate_json(extracted_issue_json)
    authority = AuthorityContact.model_validate_json(authority_contact_json)

    complaint = FinalComplaint(
        run_id=media.run_id,
        status=ComplaintStatus.VALIDATED,
        source_url=str(media.media_url),
        platform=media.platform,
        reporter_handle=media.reporter_handle,
        posted_at=media.posted_at,
        issue_category=issue.category,
        severity=issue.severity,
        issue_location=issue.location_resolved or str(media.geotag or "unknown"),
        issue_description=issue.description,
        evidence_urls=[str(media.media_url)],
        authority_name=authority.department_name,
        authority_code=authority.department_code,
        submission_endpoint=authority.submission_email,
    )

    logger.info(
        "[dummy_complaint_assembly_tool] FinalComplaint assembled  run_id=%s  status=%s",
        complaint.run_id,
        complaint.status,
    )
    return complaint.model_dump_json()


# ===========================================================================
# SECTION 3 — TOOL REGISTRY
# ===========================================================================
# Register every tool the agent is allowed to call.
# Sub-teams: add your real tool functions here when they are ready.
# Import them from app/tools/<your_pair>/<module>.py.

TOOL_REGISTRY = [
    dummy_vision_tool,
    dummy_geo_resolution_tool,
    dummy_authority_routing_tool,
    dummy_complaint_assembly_tool,
    # pair_b: from app.tools.pair_b.vision import vision_tool; add vision_tool
    # pair_d: from app.tools.pair_d.routing import routing_tool; add routing_tool
    # trio_c: from app.tools.trio_c.assembly import assembly_tool; add assembly_tool
]


# ===========================================================================
# SECTION 4 — AGENT FACTORY
# ===========================================================================

def build_agent(extra_tools: Optional[list] = None) -> CodeAgent:
    """
    Constructs and returns a configured CodeAgent instance.

    Args:
        extra_tools: Optional list of additional @tool-decorated functions to
            register on top of TOOL_REGISTRY.  Useful for integration tests.

    Returns:
        A ready-to-run smolagents.CodeAgent.
    """
    llm   = _build_llm()
    tools = TOOL_REGISTRY + (extra_tools or [])

    agent = CodeAgent(
        tools=tools,
        model=llm,
        # Allow the agent to import these standard libs in its generated code.
        additional_authorized_imports=["json", "pydantic", "datetime", "uuid"],
        # Keep a rolling window of the last N steps for long pipelines.
        max_steps=15,
        # Surface intermediate reasoning to the logger (set False in prod).
        verbosity_level=1,
    )

    logger.info("CodeAgent built  tools=%d", len(tools))
    return agent


# ===========================================================================
# SECTION 5 — ORCHESTRATION ENTRY-POINT
# ===========================================================================

def run_complaint_pipeline(media: MediaMetadata) -> FinalComplaint:
    """
    Main entry-point.  Accepts a MediaMetadata object, runs the full agentic
    pipeline, and returns a FinalComplaint.

    Args:
        media: Populated MediaMetadata instance representing the social-media
               post to process.

    Returns:
        FinalComplaint with status VALIDATED or SUBMITTED (or FAILED on error).

    Raises:
        ValueError: If the agent returns output that cannot be parsed as a
                    FinalComplaint.
    """
    agent = build_agent()

    # Serialise the input so the agent can embed it in generated code calls.
    media_json = media.model_dump_json()

    # The task prompt instructs the agent on the expected call sequence.
    # The CodeAgent will write Python code that calls the registered tools in
    # the correct order, passing outputs from one tool to the next.
    task_prompt = f"""
You are processing a civic media submission for the Agentic Civic Engagement Framework.

Your goal is to produce a FinalComplaint JSON string by calling the tools in this order:
1. Call `dummy_vision_tool` with the media metadata JSON below to detect the issue.
2. Call `dummy_geo_resolution_tool` with the ExtractedIssue JSON to resolve the location.
3. Call `dummy_authority_routing_tool` with the resolved ExtractedIssue JSON to find the authority.
4. Call `dummy_complaint_assembly_tool` with all three JSON strings to produce the FinalComplaint.
5. Return ONLY the final JSON string from step 4. Do not add any explanation.

Media metadata JSON (input):
{media_json}

Remember:
- Each tool returns a JSON string.  Pass that string directly to the next tool.
- Do NOT attempt to parse or modify the JSON between tool calls.
- If any tool raises an exception, stop and return a JSON object with a single key
  "error" describing what went wrong.
"""

    logger.info("Starting pipeline  run_id=%s", media.run_id)
    raw_output: str = agent.run(task_prompt)
    logger.info("Agent run complete  run_id=%s", media.run_id)

    # ------------------------------------------------------------------
    # Parse agent output
    # ------------------------------------------------------------------
    try:
        complaint = FinalComplaint.model_validate_json(raw_output)
    except Exception as parse_error:
        # Attempt to detect error passthrough from the agent.
        try:
            error_payload = json.loads(raw_output)
            error_msg = error_payload.get("error", str(raw_output))
        except Exception:
            error_msg = str(raw_output)

        logger.error("Pipeline failed  run_id=%s  error=%s", media.run_id, error_msg)

        # Return a FAILED complaint so callers always receive a FinalComplaint.
        complaint = FinalComplaint(
            run_id=media.run_id,
            status=ComplaintStatus.FAILED,
            source_url=str(media.media_url),
            platform=media.platform,
            posted_at=media.posted_at,
            issue_category=IssueCategory.UNKNOWN,
            severity=SeverityLevel.LOW,
            issue_location="unresolved",
            issue_description="Pipeline failed — see validation_errors for details.",
            authority_name="unresolved",
            authority_code="unresolved",
            validation_errors=[f"Agent output parse error: {error_msg}"],
        )

    return complaint


# ===========================================================================
# SECTION 6 — CLI SMOKE-TEST
# ===========================================================================

if __name__ == "__main__":
    """
    Quick smoke-test.  Run with:
        python -m app.orchestrator
    or
        HF_TOKEN=hf_xxx python app/orchestrator.py
    """
    sample_media = MediaMetadata(
        media_url="https://example.com/sample_waste_image.jpg",  # type: ignore[arg-type]
        media_type=MediaType.IMAGE,
        platform="twitter",
        posted_at=datetime(2024, 11, 14, 10, 30, 0, tzinfo=timezone.utc),
        reporter_handle="@concerned_citizen",
        geotag="Dwarka Sector 12, New Delhi",
        caption="Look at this garbage dump near the railway station! #SwachhBharat",
    )

    result = run_complaint_pipeline(sample_media)

    print("\n" + "=" * 60)
    print("PIPELINE RESULT")
    print("=" * 60)
    print(result.model_dump_json(indent=2))