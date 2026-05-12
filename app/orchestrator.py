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

from smolagents import CodeAgent, InferenceClientModel, LiteLLMModel, tool
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
        return LiteLLMModel(model_id=model_id, api_key=api_key)
    
    # Update HfApiModel to InferenceClientModel
    model_id = os.getenv("HF_MODEL_ID", "Qwen/Qwen2.5-72B-Instruct")
    token    = os.getenv("HF_TOKEN")
    return InferenceClientModel(model_id=model_id, token=token)


@tool
def dummy_vision_tool(media_metadata_json: str) -> str:
    """
    DUMMY implementation to demonstrate the vision extraction step.

    Args:
        media_metadata_json: A JSON string containing the MediaMetadata object.
    """
    data     = json.loads(media_metadata_json)
    run_id   = data["run_id"]

    issue = ExtractedIssue(
        run_id=run_id,
        category=IssueCategory.SOLID_WASTE,
        severity=3,
        location_raw="Near Railway Station Rd, Sector 12",
        location_resolved=None,
        description="Large accumulation of mixed solid waste visible on the roadside.",
        detected_objects=["plastic bags", "construction debris", "organic waste"],
        confidence_score=0.91,
        vision_model_id="dummy-v0",
    )

    logger.info("[dummy_vision_tool] ExtractedIssue built  run_id=%s", run_id)
    return issue.model_dump_json()


@tool
def dummy_geo_resolution_tool(extracted_issue_json: str) -> str:
    """
    DUMMY implementation to demonstrate geographic resolution.

    Args:
        extracted_issue_json: A JSON string containing the ExtractedIssue object.
    """
    issue_data = json.loads(extracted_issue_json)
    issue_data["location_resolved"] = "Sector 12, Dwarka, New Delhi — 110078"
    updated_issue = ExtractedIssue.model_validate(issue_data)
    return updated_issue.model_dump_json()


@tool
def dummy_authority_routing_tool(extracted_issue_json: str) -> str:
    """
    DUMMY implementation to demonstrate authority lookup.

    Args:
        extracted_issue_json: A JSON string containing the ExtractedIssue object.
    """
    issue = ExtractedIssue.model_validate_json(extracted_issue_json)
    contact = AuthorityContact(
        run_id=issue.run_id,
        department_name="South Delhi Municipal Corporation — Solid Waste Management",
        department_code="SDMC-SWM",
        submission_email="swm.complaints@sdmc.delhi.gov.in",
        submission_api_url=None,
        portal_url="https://mcdonline.nic.in/portal",
        jurisdiction="South Delhi Municipal Zone",
        escalation_authority="Delhi Pollution Control Committee",
        sla_days=21,
    )
    return contact.model_dump_json()


@tool
def dummy_complaint_assembly_tool(
    media_metadata_json: str,
    extracted_issue_json: str,
    authority_contact_json: str,
) -> str:
    """
    DUMMY implementation to demonstrate the final complaint drafting.

    Args:
        media_metadata_json: JSON string of the MediaMetadata.
        extracted_issue_json: JSON string of the ExtractedIssue.
        authority_contact_json: JSON string of the AuthorityContact.
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
    return complaint.model_dump_json()


TOOL_REGISTRY = [
    vision_tool,
    complaint_assembly_tool,
    submission_tool,
    # dummy_vision_tool,  # replaced by vision_tool
    # dummy_geo_resolution_tool,
    # dummy_authority_routing_tool,
    # dummy_complaint_assembly_tool, # replaced by complaint_assembly_tool
]


def build_agent(extra_tools: Optional[list] = None) -> CodeAgent:
    llm   = _build_llm()
    tools = TOOL_REGISTRY + (extra_tools or [])
    agent = CodeAgent(
        tools=tools,
        model=llm,
        additional_authorized_imports=[
            "json", "pydantic", "datetime", "uuid", "os", "re", 
            "groq", "geopy", "cv2", "ultralytics", "sentence_transformers", "numpy"
        ],
        max_steps=15,
        verbosity_level=1,
    )
    return agent


def run_complaint_pipeline(media: MediaMetadata) -> FinalComplaint:
    agent = build_agent()
    media_json = media.model_dump_json()
    
    task_prompt = f"""
    You are processing a civic media submission for the Agentic Civic Engagement Framework.
    
    Your goal is to produce a FinalComplaint JSON string using the available tools.
    
    Rules:
    - Always resolve the location before routing to an authority.
    - Always route to an authority before assembling the complaint.
    - Pass each tool's JSON output directly as input to the next tool — do not 
      parse or modify JSON between tool calls.
    - If any tool returns a JSON object with an "error" key, stop immediately and 
      return that JSON string as your final output.
    - Return ONLY the final FinalComplaint JSON string. No explanation.
    
    Media metadata (your starting input):
    {media_json}
    """
    
    logger.info("Starting pipeline  run_id=%s", media.run_id)
    raw_output: str = agent.run(task_prompt)

    try:
        complaint = FinalComplaint.model_validate_json(raw_output)
        
        # Wire validators
        errors = validate_final_complaint(complaint)
        if errors:
            complaint.validation_errors.extend(errors)
            if complaint.status != ComplaintStatus.FAILED:
                complaint.status = ComplaintStatus.FAILED
                
    except Exception as parse_error:
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
            validation_errors=[f"Agent output parse error: {str(raw_output)}"],
        )
    return complaint