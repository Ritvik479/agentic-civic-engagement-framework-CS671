# app/schemas/requests.py
# ---------------------------------------------------------------------------
# Pydantic request models
#
# These define the exact shape of incoming data from frontend clients.
# Used by FastAPI for:
# - validation
# - automatic parsing
# - API documentation generation
# ---------------------------------------------------------------------------

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request model for POST /confirm-location
#
# Frontend sends corrected location after user confirms map pin.
#
# Example:
# {
#   "id": "CMP-AB12CD34",
#   "final_lat": 31.7754,
#   "final_lng": 76.9862
# }
# ---------------------------------------------------------------------------
class ConfirmLocationRequest(BaseModel):
    id: str = Field(..., description="Complaint tracking ID")
    final_state: str = Field(..., description="Confirmed state name")
    final_district: str = Field(..., description="Confirmed district name")