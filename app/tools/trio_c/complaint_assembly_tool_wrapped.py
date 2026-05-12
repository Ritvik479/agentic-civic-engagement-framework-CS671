"""
app/tools/trio_c/complaint_assembly_tool_wrapped.py

smolagents @tool wrapper for the complaint assembly stage (trio_c).

Responsibility
──────────────
Merge the three upstream pipeline outputs — MediaMetadata, ExtractedIssue,
and AuthorityContact — into a single, validated FinalComplaint object that is
ready to be handed to the submission tool.

Pipeline position
─────────────────
    MediaMetadata   ─┐
    ExtractedIssue  ─┼──► complaint_assembly_tool ──► FinalComplaint (JSON str)
    AuthorityContact─┘

Internal call chain
───────────────────
    1. Deserialise all three inputs via Pydantic model_validate_json().
    2. Derive the best available location string from ExtractedIssue and
       MediaMetadata (prefer location_resolved; fall back to geotag).
    3. Call draft_complaint(issue, description, location) from
       complaint_draft_tool.py to produce the LLM-authored complaint narrative.
       NOTE: draft_complaint returns a plain str, not a structured dict.
             Severity is NOT surfaced by that function — it is computed
             internally by calculate_severity() and used only to select the
             correct authority inside the drafting step.  We therefore take
             severity directly from ExtractedIssue.severity, which was set by
             the vision tool and is already a validated SeverityLevel enum.
    4. Construct a FinalComplaint and return it as a JSON string.

The _INT_TO_SEVERITY table below is retained as defensive infrastructure for
the day draft_complaint's signature is upgraded to return structured output.
It is not called in the current implementation.

Constraints
───────────
- DO NOT modify complaint_draft_tool.py.
- DO NOT import app.context anywhere in this file.
- All sys.path manipulation lives inside complaint_draft_tool.py (legacy);
  this wrapper never reproduces it.
- On any unhandled exception, return json.dumps({"error": str(e)}) so the
  CodeAgent can detect the failure and decide whether to retry or escalate.
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
    SeverityLevel,
)
from app.tools.trio_c.complaint_draft_tool import draft_complaint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defensive severity mapping
# Kept for forward-compatibility if draft_complaint is later upgraded to
# return a structured result dict containing a numeric severity field.
# NOT used in the current implementation — see module docstring.
# ---------------------------------------------------------------------------
_INT_TO_SEVERITY: dict[int, SeverityLevel] = {
    1: SeverityLevel.LOW,
    2: SeverityLevel.MEDIUM,
    3: SeverityLevel.HIGH,
    4: SeverityLevel.CRITICAL,
}


# ---------------------------------------------------------------------------
# Helper — derive SLA days from severity (mirrors constants.SEVERITY_TO_SLA_DAYS)
# ---------------------------------------------------------------------------
def _sla_days_for(severity: SeverityLevel) -> int:
    """Return the SLA day count for a given SeverityLevel from constants."""
    return SEVERITY_TO_SLA_DAYS.get(severity.value, 30)


# ---------------------------------------------------------------------------
# @tool
# ---------------------------------------------------------------------------

@tool
def complaint_assembly_tool(
    media_metadata_json: str,
    extracted_issue_json: str,
    authority_contact_json: str,
) -> str:
    """
    Assemble a complete, submission-ready FinalComplaint from the three upstream
    pipeline outputs.

    This is the final reasoning-layer step before submission.  It takes the raw
    ingestion metadata, the vision-model's structured issue analysis, and the
    routed authority contact details, then:
      - Resolves the best available location string.
      - Calls the LLM-powered drafting tool to produce formal complaint text.
      - Packages everything into a validated FinalComplaint object.

    Call this tool AFTER all three of the following have completed:
      - The vision tool has produced an ExtractedIssue with location_resolved
        populated by the geo-resolution tool.
      - The authority routing tool has produced an AuthorityContact.

    Args:
        media_metadata_json: JSON string of a MediaMetadata object.
            Must be produced by MediaMetadata.model_dump_json().
            Provides source URL, platform, reporter handle, posted_at, and the
            raw geotag fallback location.

        extracted_issue_json: JSON string of an ExtractedIssue object.
            Must be produced by ExtractedIssue.model_dump_json().
            Provides category, severity, location_resolved, description, and
            detected_objects.  location_resolved should be populated by the
            geo-resolution tool before this tool is called; if it is None the
            tool falls back to MediaMetadata.geotag.

        authority_contact_json: JSON string of an AuthorityContact object.
            Must be produced by AuthorityContact.model_dump_json().
            Provides department_name, department_code, submission_email,
            submission_api_url, and sla_days.

    Returns:
        On success: JSON string of a FinalComplaint with status=VALIDATED.
            Parse with FinalComplaint.model_validate_json().
        On failure: JSON string of the form {"error": "<message>"}.
            The CodeAgent should treat this as a pipeline failure and either
            retry with corrected inputs or escalate to human review.

    Example (CodeAgent generated code):
        result = complaint_assembly_tool(
            media_metadata_json=media_json,
            extracted_issue_json=issue_json,
            authority_contact_json=authority_json,
        )
        if "error" not in result:
            complaint = FinalComplaint.model_validate_json(result)
    """
    try:
        # ------------------------------------------------------------------
        # Step 1 — Deserialise all three inputs
        # ------------------------------------------------------------------
        media     = MediaMetadata.model_validate_json(media_metadata_json)
        issue     = ExtractedIssue.model_validate_json(extracted_issue_json)
        authority = AuthorityContact.model_validate_json(authority_contact_json)

        logger.info(
            "[complaint_assembly_tool] Inputs parsed  run_id=%s  category=%s  authority=%s",
            media.run_id,
            issue.category.value,
            authority.department_code,
        )

        # ------------------------------------------------------------------
        # Step 2 — Resolve best available location string
        # Prefer the geo-resolved address from ExtractedIssue; fall back to
        # the raw geotag from MediaMetadata; use a placeholder as last resort.
        # ------------------------------------------------------------------
        location: str = (
            issue.location_resolved
            or media.geotag
            or UNKNOWN_LOCATION_PLACEHOLDER
        )

        if not issue.location_resolved:
            logger.warning(
                "[complaint_assembly_tool] location_resolved is None — "
                "falling back to geotag=%r  run_id=%s",
                media.geotag,
                media.run_id,
            )

        # ------------------------------------------------------------------
        # Step 3 — Call draft_complaint to produce formal complaint narrative
        #
        # Signature:  draft_complaint(issue: str, description: str, location: str) -> str
        #
        # draft_complaint returns a plain str (the LLM-authored narrative).
        # It does NOT return severity — severity is used internally only to
        # select the correct authority within the drafting chain.
        # We therefore read severity from ExtractedIssue.severity directly.
        # ------------------------------------------------------------------
        complaint_text: str = draft_complaint(
            issue=issue.category.value,        # e.g. "solid_waste"
            description=issue.description,     # vision model's factual description
            location=location,
        )

        # Guard against the known failure string returned when authority
        # lookup fails inside draft_complaint.
        if complaint_text == "Unable to determine correct authority for this issue.":
            logger.warning(
                "[complaint_assembly_tool] draft_complaint returned authority-unknown sentinel  "
                "run_id=%s — using ExtractedIssue.description as fallback narrative",
                media.run_id,
            )
            # Fall back to the vision model's raw description rather than
            # returning an error, so the pipeline can still submit something.
            complaint_text = issue.description

        elif complaint_text == "Failed to generate complaint.":
            logger.warning(
                "[complaint_assembly_tool] LLM call failed inside draft_complaint  run_id=%s"
                " — using ExtractedIssue.description as fallback narrative",
                media.run_id,
            )
            complaint_text = issue.description

        # ------------------------------------------------------------------
        # Step 4 — Determine severity
        # ExtractedIssue.severity is already a validated SeverityLevel enum
        # set by the vision tool.  draft_complaint does not return severity.
        # ------------------------------------------------------------------
        severity: SeverityLevel = issue.severity

        # ------------------------------------------------------------------
        # Step 5 — Resolve submission endpoint
        # Prefer the API URL; fall back to email.
        # ------------------------------------------------------------------
        submission_endpoint: str | None = (
            str(authority.submission_api_url)
            if authority.submission_api_url
            else authority.submission_email
        )

        # ------------------------------------------------------------------
        # Step 6 — Construct FinalComplaint
        # ------------------------------------------------------------------
        complaint = FinalComplaint(
            run_id=media.run_id,
            status=ComplaintStatus.VALIDATED,

            # Source fields — flattened from MediaMetadata
            source_url=str(media.media_url),
            platform=media.platform,
            reporter_handle=media.reporter_handle,
            posted_at=media.posted_at,

            # Issue fields — flattened from ExtractedIssue
            issue_category=issue.category,
            severity=severity,
            issue_location=location,
            issue_description=complaint_text,
            evidence_urls=[str(media.media_url)],

            # Authority fields — flattened from AuthorityContact
            authority_name=authority.department_name,
            authority_code=authority.department_code,
            submission_endpoint=submission_endpoint,
        )

        logger.info(
            "[complaint_assembly_tool] FinalComplaint assembled  run_id=%s  "
            "status=%s  severity=%s  authority=%s",
            complaint.run_id,
            complaint.status,
            complaint.severity,
            complaint.authority_code,
        )

        return complaint.model_dump_json()

    except Exception as e:
        logger.exception(
            "[complaint_assembly_tool] Unhandled exception  error=%s", e
        )
        return json.dumps({"error": str(e)})
