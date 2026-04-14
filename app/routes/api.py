# app/routes/api.py
# ---------------------------------------------------------------------------
# FastAPI routes for frontend-mobile communication
#
# FIXED VERSION:
# - Matches frontend contract exactly
# - Non-blocking async processing
# - Immediate tracking ID return
# - Supports status polling logs
# - Adds confirm-location endpoint
# ---------------------------------------------------------------------------

import os
import uuid

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    BackgroundTasks
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.orchestrator import run_agent
from app.db.database import (
    fetch_complaint,
    fetch_slim_complaints,
    fetch_logs,
    create_pending_complaint,
    insert_log,
    update_status
)

# ---------------------------------------------------------------------------
# Router setup
# ---------------------------------------------------------------------------
router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Request schema for confirm-location
# ---------------------------------------------------------------------------
from app.schemas.requests import ConfirmLocationRequest
from app.schemas.responses import (
    ProcessResponse,
    StatusResponse,
    ConfirmLocationResponse
)


# ---------------------------------------------------------------------------
# POST /api/process
#
# Frontend sends:
# - video file
# - lat
# - lng
#
# Returns immediately:
# {
#   "id": "CMP-XXXX",
#   "status": "pending"
# }
#
# Background processing continues asynchronously.
# ---------------------------------------------------------------------------
@router.post("/process")
async def process_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    lat: float = Form(...),
    lng: float = Form(...),
    user_id: str = Form(default="anonymous"),
):
    # -----------------------------------------------------------------------
    # Validate uploaded file
    # -----------------------------------------------------------------------
    if not video.content_type.startswith("video/"):
        raise HTTPException(
            status_code=400,
            detail="Only video files accepted."
        )

    # -----------------------------------------------------------------------
    # Generate tracking ID BEFORE starting pipeline
    # Frontend needs this immediately
    # -----------------------------------------------------------------------
    tracking_id = "CMP-" + uuid.uuid4().hex[:8].upper()

    # -----------------------------------------------------------------------
    # Save uploaded video file
    # -----------------------------------------------------------------------
    ext = os.path.splitext(video.filename or "video.mp4")[1] or ".mp4"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    contents = await video.read()
    with open(filepath, "wb") as f:
        f.write(contents)

    abs_path = os.path.abspath(filepath)

    print(f"[API] Saved video: {abs_path}")

    # -----------------------------------------------------------------------
    # Create complaint immediately in DB
    # Prevents early polling from failing
    # -----------------------------------------------------------------------
    create_pending_complaint(
        tracking_id=tracking_id,
        user_id=user_id,
        video_path=abs_path
    )

    # -----------------------------------------------------------------------
    # Add first log entry
    # -----------------------------------------------------------------------
    insert_log(tracking_id, "Video uploaded successfully.")

    # -----------------------------------------------------------------------
    # Start async background processing
    # -----------------------------------------------------------------------
    background_tasks.add_task(
        run_agent,
        video_path=abs_path,
        tracking_id=tracking_id,
        user_location=f"{lat},{lng}",
        user_id=user_id
    )

    # -----------------------------------------------------------------------
    # Return immediately
    # -----------------------------------------------------------------------
    return JSONResponse(content={
        "id": tracking_id,
        "status": "pending"
    })


# ---------------------------------------------------------------------------
# GET /api/status/{tracking_id}
#
# Frontend polls this repeatedly
#
# Returns:
# {
#   "status": "detecting_issue",
#   "logs": [...]
# }
# ---------------------------------------------------------------------------
@router.get("/status/{tracking_id}")
def get_status(tracking_id: str):
    complaint = fetch_complaint(tracking_id)

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Tracking ID not found."
        )

    logs = fetch_logs(tracking_id)

    return JSONResponse(content={
        "status": complaint["submission_status"],
        "logs": logs
    })


# ---------------------------------------------------------------------------
# POST /api/confirm-location
#
# Frontend sends corrected user-confirmed location
#
# {
#   "id": "...",
#   "final_lat": ...,
#   "final_lng": ...
# }
#
# Returns:
# {
#   "status": "authority_mapped"
# }
# ---------------------------------------------------------------------------
@router.post("/confirm-location")
def confirm_location(data: ConfirmLocationRequest):
    complaint = fetch_complaint(data.id)

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Tracking ID not found."
        )

    # -----------------------------------------------------------------------
    # Save corrected location
    # For now stored as lat,lng string
    # Later this can be reverse-geocoded
    # -----------------------------------------------------------------------
    corrected_location = f"{data.final_lat},{data.final_lng}"

    # TEMP placeholder:
    # update DB location later via dedicated DB function if needed
    insert_log(data.id, f"Location confirmed: {corrected_location}")

    # -----------------------------------------------------------------------
    # Update status
    # -----------------------------------------------------------------------
    update_status(data.id, "authority_mapped")

    return JSONResponse(content={
        "status": "authority_mapped"
    })


# ---------------------------------------------------------------------------
# GET /api/complaint/{tracking_id}
# Full complaint detail view
# ---------------------------------------------------------------------------
@router.get("/complaint/{tracking_id}")
def get_full_complaint(tracking_id: str):
    complaint = fetch_complaint(tracking_id)

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Complaint not found."
        )

    return JSONResponse(content=complaint)


# ---------------------------------------------------------------------------
# GET /api/complaints?user_id=xyz
# Complaint history list
# ---------------------------------------------------------------------------
@router.get("/complaints")
def list_complaints(user_id: str = None):
    slim_list = fetch_slim_complaints(user_id=user_id)

    return JSONResponse(content={
        "complaints": slim_list,
        "count": len(slim_list)
    })


# ---------------------------------------------------------------------------
# GET /api/health
# Health check endpoint
# ---------------------------------------------------------------------------
@router.get("/health")
def health():
    return {
        "status": "ok",
        "server": "Civic Engagement Backend"
    }