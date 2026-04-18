# app/context.py
# ---------------------------------------------------------------------------
# Shared complaint context object passed through all agents
# Pair B owns this file
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ComplaintContext:

    # Core metadata
    tracking_id: str = ""
    user_id: str = ""
    video_path: str = ""
    video_url: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    user_issue_description: str = ""
    landmark: str = ""

    # Pair D outputs
    issue_type: str = ""
    state: str = ""
    district: str = ""
    location_label: str = ""       # human-readable label, e.g. "Shimla, HP"

    # FIX: severity now validated — was unconstrained int (could be -1 or 999)
    severity: int = 0
    transcript: str = ""

    # Trio C outputs
    authority_name: str = ""
    authority_email: str = ""
    authority_portal: str = ""
    complaint_text: str = ""
    authority_level: str = "level1"
    authority_level_num: int = 1

    # Pair B outputs
    submission_status: str = "pending"
    submission_screenshot: str = ""
    complaint_ref_id: str = ""        # ADD — assigned by portal after submission
    authority_phone: str = ""         # ADD — for WhatsApp dispatch
    full_name: str = ""               # ADD

    # Error tracking
    error: Optional[str] = None

    def __post_init__(self):
        # Enforce severity range 0–5
        # Trio C or Pair D sets this; a value outside range is a bug, not user input
        if not (0 <= self.severity <= 5):
            self.severity = max(0, min(5, self.severity))