"""
app/tools/trio_c/routing_tool_wrapped.py
"""

from __future__ import annotations
import json
import logging
from smolagents import tool
from app.constants import CATEGORY_TO_DEFAULT_DEPT
from app.schemas.issue_schema import AuthorityContact, ExtractedIssue
from app.tools.trio_c.authority_lookup_tool import lookup_authority

logger = logging.getLogger(__name__)

from typing import Any

@tool
def route_to_authority(run_id: str, category: str, location_resolved: str, severity: Any = 3) -> str:
    """
    Maps issue to government dept based on category and location.
    Args:
        run_id: The unique ID for this report.
        category: The category of the issue (e.g. 'water_pollution').
        location_resolved: The resolved location string (e.g. 'District, State').
        severity: The severity score (1-4).
    """
    try:
        # Robustness: ensure severity is int
        try:
            severity_int = int(severity)
        except (ValueError, TypeError):
            severity_int = 3

        parts = [p.strip() for p in location_resolved.split(",")]
        district = parts[0] if len(parts) > 0 else "Unknown"
        state = parts[1] if len(parts) > 1 else "Unknown"

        auth_data = lookup_authority(
            issue=category,
            state=state,
            district=district,
            severity=severity_int
        )

        contact = AuthorityContact(
            run_id=run_id,
            department_name=auth_data["authority_name"],
            department_code=CATEGORY_TO_DEFAULT_DEPT.get(category, "GENERIC-CIV"),
            submission_email=auth_data.get("authority_email"),
            submission_api_url=None,
            portal_url=auth_data.get("authority_portal"),
            jurisdiction=f"{district}, {state}",
            escalation_authority=None,
            sla_days=30
        )
        return contact.model_dump_json()
    except Exception as e:
        return json.dumps({"error": str(e)})
