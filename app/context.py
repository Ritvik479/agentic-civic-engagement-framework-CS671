# app/context.py
# ---------------------------------------------------------------------------
# Shared complaint context object passed through all agents
# Pair B owns this file
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from typing import Optional


@dataclass
class ComplaintContext:

    # Core metadata
    tracking_id: str = ""
    user_id: str = ""
    video_path: str = ""

    # Pair D outputs
    issue_type: str = ""
    location: str = ""
    severity: int = 0
    transcript: str = ""

    # Trio C outputs
    authority_name: str = ""
    authority_email: str = ""
    authority_portal: str = ""
    complaint_text: str = ""

    # Pair B / Pair E outputs
    submission_status: str = "pending"
    submission_screenshot: str = ""

    # Error tracking
    error: Optional[str] = None