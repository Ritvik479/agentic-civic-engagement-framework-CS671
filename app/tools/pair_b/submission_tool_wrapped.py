"""
app/tools/pair_b/submission_tool_wrapped.py
"""

from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from smolagents import tool
from app.schemas.issue_schema import FinalComplaint, ComplaintStatus, IssueCategory
from app.tools.pair_b.submission_agent_tool import submit_complaint

logger = logging.getLogger(__name__)

import asyncio

from typing import Any

@tool
def submission_tool(
    run_id: str,
    authority_name: str,
    authority_code: str,
    submission_endpoint: str,
    authority_portal: str,
    description: str,
    category: str,
    severity: Any,
    media_url: str,
    platform: str,
    posted_at: str,
) -> str:
    """
    Submits the complaint to government portals and email.
    Args:
        run_id: Unique ID.
        authority_name: Name of authority.
        authority_code: Department code.
        submission_endpoint: Email/API.
        authority_portal: URL.
        description: Drafted complaint text.
        category: Issue category.
        severity: Score.
        media_url: Evidence URL.
        platform: Source platform.
        posted_at: ISO timestamp.
    """
    try:
        try:
            severity_int = max(1, min(5, int(severity)))
        except (ValueError, TypeError):
            severity_int = 3

        ctx = {
            "tracking_id":      run_id,
            "authority_name":    authority_name,
            "authority_email":   submission_endpoint or "",
            "authority_portal":  authority_portal or "",
            "complaint_text":    description,
            "issue_type":        category,
            "severity":          severity_int,
        }
        
        # 1. Dispatch in a separate thread to avoid Playwright sync/async conflict
        # Use asyncio.to_thread if available (Python 3.9+) or a safe loop check
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # This is the fix for "Playwright Sync API inside the asyncio loop"
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(submit_complaint, ctx).result()
        else:
            result = submit_complaint(ctx)
        
        # 2. Build final response
        status = ComplaintStatus.SUBMITTED if result.get("success") else ComplaintStatus.FAILED
        
        complaint = FinalComplaint(
            run_id=run_id,
            status=status,
            source_url=media_url,
            platform=platform,
            posted_at=posted_at,
            issue_category=IssueCategory(category),
            severity=severity_int,
            issue_location="See Description",
            issue_description=description,
            evidence_urls=[media_url],
            authority_name=authority_name,
            authority_code=authority_code,
            authority_portal=authority_portal if authority_portal else None,
            submission_endpoint=submission_endpoint if submission_endpoint else None,
            complaint_id=result.get("complaint_ref_id"),
            submitted_at=datetime.now(timezone.utc) if result.get("success") else None,
            submission_response=result,
            validation_errors=[result.get("error")] if not result.get("success") else []
        )

        return complaint.model_dump_json()
        
    except Exception as e:
        logger.exception("[submission_tool] Fatal error")
        return json.dumps({"error": str(e)})