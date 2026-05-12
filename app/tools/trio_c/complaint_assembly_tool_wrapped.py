"""
app/tools/trio_c/complaint_assembly_tool_wrapped.py
"""

from __future__ import annotations
import json
import logging
from smolagents import tool
from app.schemas.issue_schema import AuthorityContact, ComplaintStatus, ExtractedIssue, FinalComplaint, MediaMetadata, IssueCategory
from app.tools.trio_c.complaint_draft_tool import draft_complaint

logger = logging.getLogger(__name__)

from typing import Any

@tool
def complaint_assembly_tool(
    run_id: str,
    media_url: str,
    platform: str,
    posted_at: str,
    category: str,
    severity: Any,
    location_resolved: str,
    description: str,
    authority_name: str,
    authority_code: str,
    authority_portal: str = "",
    submission_endpoint: str = "",
) -> str:
    """
    Drafts the final formal complaint text and assembles the FinalComplaint object.
    Args:
        run_id: Unique ID.
        media_url: Original media URL.
        platform: Platform name.
        posted_at: ISO timestamp.
        category: Issue category value.
        severity: Severity score.
        location_resolved: Resolved location.
        description: Initial description.
        authority_name: Targeted authority.
        authority_code: Department code.
        authority_portal: Portal URL if any.
        submission_endpoint: Email or API endpoint.
    """
    try:
        try:
            severity_int = int(severity)
        except (ValueError, TypeError):
            severity_int = 3

        complaint_text = draft_complaint(
            issue=category,        
            description=description,     
            location=location_resolved or "Unknown",
        )

        complaint = FinalComplaint(
            run_id=run_id,
            status=ComplaintStatus.VALIDATED,
            source_url=media_url,
            platform=platform,
            posted_at=posted_at,
            issue_category=IssueCategory(category),
            severity=severity_int,
            issue_location=location_resolved or "Unknown",
            issue_description=complaint_text or description,
            evidence_urls=[media_url],
            authority_name=authority_name,
            authority_code=authority_code,
            authority_portal=authority_portal if authority_portal else None,
            submission_endpoint=submission_endpoint,
        )
        return complaint.model_dump_json()
    except Exception as e:
        logger.exception("[complaint_assembly_tool] Error")
        return json.dumps({"error": str(e)})
