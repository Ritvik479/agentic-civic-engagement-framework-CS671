# app/schemas/responses.py
# ---------------------------------------------------------------------------
# Pydantic response models
#
# These define the exact shape of outgoing API responses sent to frontend.
# Used by FastAPI for:
# - response validation
# - OpenAPI docs generation
# - consistent API contracts
# ---------------------------------------------------------------------------

from typing import List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Response for POST /process
#
# Returned immediately after upload succeeds.
#
# Example:
# {
#   "id": "CMP-AB12CD34",
#   "status": "pending"
# }
# ---------------------------------------------------------------------------
class ProcessResponse(BaseModel):
    id: str = Field(..., description="Generated complaint tracking ID")
    status: str = Field(..., description="Initial complaint status")


# ---------------------------------------------------------------------------
# Response for GET /status/{tracking_id}
#
# Frontend polls this repeatedly.
#
# Example:
# {
#   "status": "detecting_issue",
#   "logs": [
#       "Video uploaded successfully.",
#       "Issue detection started."
#   ]
# }
# ---------------------------------------------------------------------------
class StatusResponse(BaseModel):
    status: str = Field(..., description="Current complaint status")
    logs: List[str] = Field(..., description="Ordered progress log messages")


# ---------------------------------------------------------------------------
# Response for POST /confirm-location
#
# Example:
# {
#   "status": "authority_mapped"
# }
# ---------------------------------------------------------------------------
class ConfirmLocationResponse(BaseModel):
    status: str = Field(..., description="Updated complaint status")


# ---------------------------------------------------------------------------
# Response for GET /complaint/{tracking_id}
#
# Full complaint detail response.
# Used when frontend opens detailed complaint page.
# ---------------------------------------------------------------------------
class ComplaintDetailResponse(BaseModel):
    tracking_id: str
    user_id: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    video_path: Optional[str]

    issue_type: Optional[str]
    location: Optional[str]
    severity: Optional[int]
    transcript: Optional[str]

    authority_name: Optional[str]
    authority_email: Optional[str]
    authority_portal: Optional[str]
    complaint_text: Optional[str]

    submission_status: Optional[str]
    submission_screenshot: Optional[str]

    error: Optional[str]


# ---------------------------------------------------------------------------
# Slim complaint summary item
# Used in complaint list dashboard
# ---------------------------------------------------------------------------
class ComplaintSummaryItem(BaseModel):
    tracking_id: str
    submission_status: str
    issue_type: Optional[str]
    location: Optional[str]
    severity: Optional[int]
    created_at: Optional[str]


# ---------------------------------------------------------------------------
# Response for GET /complaints
#
# Example:
# {
#   "complaints": [...],
#   "count": 5
# }
# ---------------------------------------------------------------------------
class ComplaintListResponse(BaseModel):
    complaints: List[ComplaintSummaryItem]
    count: int


# ---------------------------------------------------------------------------
# Health check response
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str
    server: str