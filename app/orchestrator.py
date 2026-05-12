"""
app/orchestrator.py

smolagents CodeAgent orchestrator for the Agentic Civic Engagement Framework.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from smolagents import ToolCallingAgent, InferenceClientModel, LiteLLMModel, tool
from smolagents.models import MessageRole

from app.schemas.issue_schema import (
    AuthorityContact,
    ComplaintStatus,
    ExtractedIssue,
    FinalComplaint,
    IssueCategory,
    MediaMetadata,
    MediaType,
)

# New imports for tools and validators
from app.tools.pair_d.vision_tool_wrapped import vision_tool
from app.tools.trio_c.routing_tool_wrapped import route_to_authority
from app.tools.trio_c.complaint_assembly_tool_wrapped import complaint_assembly_tool
from app.tools.pair_b.submission_tool_wrapped import submission_tool
from app.validators import validate_final_complaint

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("orchestrator")


def _build_llm() -> InferenceClientModel | LiteLLMModel: # Update return type hint
    backend = os.getenv("ORCHESTRATOR_LLM", "hf").lower()
    if backend == "litellm":
        model_id = os.getenv("LITELLM_MODEL", "openai/gpt-4o")
        api_key  = os.getenv("LITELLM_API_KEY")
        base_url = os.getenv("LITELLM_BASE_URL")
        return LiteLLMModel(model_id=model_id, api_key=api_key, base_url=base_url)
    
    # Update HfApiModel to InferenceClientModel
    model_id = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-72B-Instruct")
    token    = os.getenv("HF_TOKEN")
    return InferenceClientModel(model_id=model_id, token=token)


TOOL_REGISTRY = [
    vision_tool,
    route_to_authority,
    complaint_assembly_tool,
    submission_tool,
]


def build_agent(extra_tools: Optional[list] = None) -> ToolCallingAgent:
    llm   = _build_llm()
    tools = TOOL_REGISTRY + (extra_tools or [])
    agent = ToolCallingAgent(
        tools=tools,
        model=llm,
        max_steps=10, 
        verbosity_level=1,
    )
    return agent


def run_complaint_pipeline(media: MediaMetadata) -> FinalComplaint:
    agent = build_agent()
    
    # ── Step 0: Prep simplified inputs for the agent ──
    # We pass individual fields to make it easy for the agent to call tools
    # without having to manage complex JSON strings manually.
    initial_args = {
        "run_id":    str(media.run_id),
        "media_url": str(media.media_url),
        "geotag":    media.geotag or "",
        "caption":   media.caption or "",
        "platform":  media.platform,
        "posted_at": media.posted_at.isoformat(),
    }
    
    task_prompt = f"""Process the civic report for Run ID: {initial_args['run_id']}.

IMPORTANT: You MUST use strictly valid JSON for tool calls. Use DOUBLE QUOTES (") for all keys and string values. Single quotes (') are NOT allowed in the JSON structure.

Follow these steps strictly:
1. Call 'vision_tool' using 'run_id', 'media_url', 'geotag', and 'caption' from the provided variables. It returns a JSON string with issue details.
2. Parse the JSON from 'vision_tool' to get 'category', 'location_resolved', 'description', and 'severity'.
3. Call 'route_to_authority' using 'run_id', 'category', 'location_resolved', and 'severity' to find the government department. It returns a JSON string with authority details.
4. Parse the JSON from 'route_to_authority' to get 'department_name', 'department_code', 'portal_url', and 'submission_email'.
5. Call 'complaint_assembly_tool' to draft the formal text and create the complaint object. Pass all required fields collected so far.
6. Finally, call 'submission_tool' with the assembled complaint details to submit it.
7. Return the final JSON from 'submission_tool' as your final answer. You MUST provide the full JSON object, not a text summary."""
    
    logger.info("Starting pipeline  run_id=%s", media.run_id)
    raw_output: str = agent.run(task_prompt, additional_args=initial_args)

    try:
        # Check if the agent returned an error JSON or a plain string instead of FinalComplaint
        try:
            parsed = json.loads(raw_output)
            if isinstance(parsed, dict) and "error" in parsed:
                raise ValueError(f"Agent reported error: {parsed['error']}")
            if isinstance(parsed, dict) and "answer" in parsed:
                # Agent used final_answer with a string — try to find the last tool output
                # Or just treat the raw_output as the source for model_validate if it looks like JSON
                pass
        except json.JSONDecodeError:
            pass 

        # Robustness: If raw_output is not valid JSON but the pipeline actually finished,
        # we try to reconstruct a successful object or report the parsing error.
        complaint = FinalComplaint.model_validate_json(raw_output)
        
        # Wire validators
        errors = validate_final_complaint(complaint)
        if errors:
            complaint.validation_errors.extend(errors)
            if complaint.status != ComplaintStatus.FAILED:
                complaint.status = ComplaintStatus.FAILED
                
    except Exception as parse_error:
        logger.error("Pipeline parsing failed: %s", parse_error)
        complaint = FinalComplaint(
            run_id=media.run_id,
            status=ComplaintStatus.FAILED,
            source_url=str(media.media_url),
            platform=media.platform,
            posted_at=media.posted_at,
            issue_category=IssueCategory.UNKNOWN,
            severity=1,
            issue_location="unresolved",
            issue_description="Pipeline failed — see validation_errors for details.",
            authority_name="unresolved",
            authority_code="unresolved",
            validation_errors=[f"Agent output parse error: {str(parse_error)}", f"Raw output: {str(raw_output)}"],
        )
    return complaint
