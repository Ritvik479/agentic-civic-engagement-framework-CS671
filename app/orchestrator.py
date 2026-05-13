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


def _build_llm() -> InferenceClientModel | LiteLLMModel:
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
    logger.info("Starting deterministic pipeline  run_id=%s", media.run_id)
    
    try:
        # ── Step 1: Vision ───────────────────────────────────────────────────
        logger.info("[Pipeline] Step 1: Vision Analysis")
        vision_json = vision_tool(
            run_id=str(media.run_id),
            media_url=str(media.media_url),
            geotag=media.geotag or "",
            caption=media.caption or ""
        )
        vision_res = json.loads(vision_json)
        if "error" in vision_res:
            raise ValueError(f"Vision tool failed: {vision_res['error']}")
        
        # ── Step 2: Routing ──────────────────────────────────────────────────
        logger.info("[Pipeline] Step 2: Authority Routing")
        routing_json = route_to_authority(
            run_id=str(media.run_id),
            category=vision_res["category"],
            location_resolved=vision_res["location_resolved"],
            severity=vision_res["severity"]
        )
        routing_res = json.loads(routing_json)
        if "error" in routing_res:
            raise ValueError(f"Routing tool failed: {routing_res['error']}")
        
        # ── Step 3: Assembly ─────────────────────────────────────────────────
        logger.info("[Pipeline] Step 3: Complaint Assembly")
        assembly_json = complaint_assembly_tool(
            run_id=str(media.run_id),
            media_url=str(media.media_url),
            platform=media.platform,
            posted_at=media.posted_at.isoformat(),
            category=vision_res["category"],
            severity=vision_res["severity"],
            location_resolved=vision_res["location_resolved"],
            description=vision_res["description"],
            authority_name=routing_res["department_name"],
            authority_code=routing_res["department_code"],
            authority_portal=routing_res.get("portal_url") or "",
            submission_endpoint=routing_res.get("submission_email") or ""
        )
        assembly_res = json.loads(assembly_json)
        if "error" in assembly_res:
            raise ValueError(f"Assembly tool failed: {assembly_res['error']}")
        
        # ── Step 4: Submission ───────────────────────────────────────────────
        logger.info("[Pipeline] Step 4: Submission")
        submission_json = submission_tool(
            run_id=str(media.run_id),
            authority_name=routing_res["department_name"],
            authority_code=routing_res["department_code"],
            submission_endpoint=routing_res.get("submission_email") or "",
            authority_portal=routing_res.get("portal_url") or "",
            description=assembly_res["issue_description"],
            category=vision_res["category"],
            severity=vision_res["severity"],
            media_url=str(media.media_url),
            platform=media.platform,
            posted_at=media.posted_at.isoformat()
        )
        
        complaint = FinalComplaint.model_validate_json(submission_json)
        
        # Wire validators
        errors = validate_final_complaint(complaint)
        if errors:
            complaint.validation_errors.extend(errors)
            if complaint.status != ComplaintStatus.FAILED:
                complaint.status = ComplaintStatus.FAILED
                
    except Exception as pipeline_error:
        logger.error("Pipeline failed: %s", pipeline_error)
        complaint = FinalComplaint(
            run_id=media.run_id,
            status=ComplaintStatus.FAILED,
            source_url=str(media.media_url),
            platform=media.platform,
            posted_at=media.posted_at,
            issue_category=IssueCategory.UNKNOWN,
            severity=1,
            issue_location="unresolved",
            issue_description=f"Pipeline failed: {str(pipeline_error)}",
            authority_name="unresolved",
            authority_code="unresolved",
            validation_errors=[str(pipeline_error)],
        )
    return complaint
