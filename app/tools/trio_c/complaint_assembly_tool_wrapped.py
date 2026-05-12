"""
app/tools/trio_c/complaint_assembly_tool_wrapped.py

smolagents @tool wrapper for the complaint assembly stage (trio_c).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from smolagents import tool

from app.constants import SEVERITY_TO_SLA_DAYS, UNKNOWN_LOCATION_PLACEHOLDER
from app.schemas.issue_schema import (
    AuthorityContact,
    ComplaintStatus,
    ExtractedIssue,
    FinalComplaint,
    MediaMetadata,
)
from app.tools.trio_c.complaint_draft_tool import draft_complaint

logger = logging.getLogger(__name__)


def _sla_days_for(severity: int) -> int:
    """Return the SLA day count for a given integer severity from constants."""
    return SEVERITY_TO_SLA_DAYS.get(severity, 30)


@tool
def complaint_assembly_tool(
    media_metadata_json: str,
    extracted_issue_json: str,
    authority_contact_json: str,
) -> str:
    """
    Assemble a complete, submission-ready FinalComplaint from the three upstream
    pipeline outputs.

    Args:
        media_metadata_json: JSON string of a MediaMetadata object containing 
            source media information and run identifiers.
        extracted_issue_json: JSON string of an ExtractedIssue object containing 
            the issue category, description, and resolved location from the vision tool.
        authority_contact_json: JSON string of an AuthorityContact object containing 
            department details and submission endpoints.

    Returns:
        A JSON string of a FinalComplaint object if successful, or an error JSON 
        string if the assembly fails.
    """
    try:
        media     = MediaMetadata.model_validate_json(media_metadata_json)
        issue     = ExtractedIssue.model_validate_json(extracted_issue_json)
        authority = AuthorityContact.model_validate_json(authority_contact_json)

        logger.info(
            "[complaint_assembly_tool] Inputs parsed  run_id=%s  category=%s  authority=%s",
            media.run_id,
            issue.category.value,
            authority.department_code,
        )

        location: str = (
            issue.location_resolved
            or media.geotag
            or UNKNOWN_LOCATION_PLACEHOLDER
        )

        complaint_text: str = draft_complaint(
            issue=issue.category.value,        
            description=issue.description,     
            location=location,
        )

        if complaint_text in ["Unable to determine correct authority for this issue.", "Failed to generate complaint."]:
            logger.warning(
                "[complaint_assembly_tool] draft_complaint issue  run_id=%s — using ExtractedIssue.description as fallback",
                media.run_id,
            )
            complaint_text = issue.description

        submission_endpoint: str | None = (
            str(authority.submission_api_url)
            if authority.submission_api_url
            else authority.submission_email
        )

        complaint = FinalComplaint(
            run_id=media.run_id,
            status=ComplaintStatus.VALIDATED,
            source_url=str(media.media_url),
            platform=media.platform,
            reporter_handle=media.reporter_handle,
            posted_at=media.posted_at,
            issue_category=issue.category,
            severity=issue.severity,
            issue_location=location,
            issue_description=complaint_text,
            evidence_urls=[str(media.media_url)],
            authority_name=authority.department_name,
            authority_code=authority.department_code,
            submission_endpoint=submission_endpoint,
        )

        logger.info(
            "[complaint_assembly_tool] FinalComplaint assembled  run_id=%s  status=%s  severity=%s",
            complaint.run_id,
            complaint.status,
            complaint.severity,
        )

        return complaint.model_dump_json()

    except Exception as e:
        logger.exception("[complaint_assembly_tool] Unhandled exception  error=%s", e)
        return json.dumps({"error": str(e)})