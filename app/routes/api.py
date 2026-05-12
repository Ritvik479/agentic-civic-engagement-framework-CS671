# app/routes/api.py
# ---------------------------------------------------------------------------
# FastAPI routes for frontend-mobile communication
# ---------------------------------------------------------------------------

import os
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException,
    BackgroundTasks
)
from fastapi.responses import JSONResponse

from app.orchestrator import run_complaint_pipeline
from app.db.database import (
    fetch_complaint,
    fetch_slim_complaints,
    fetch_logs,
    create_pending_complaint,
    insert_log,
    update_status,
    update_location          # new — see database.py
)
from app.schemas.issue_schema import MediaMetadata, MediaType
from app.schemas.requests import ConfirmLocationRequest
from app.schemas.responses import (
    ProcessResponse,
    StatusResponse,
    ConfirmLocationResponse,
    ComplaintDetailResponse,
    ComplaintListResponse,
)

# ---------------------------------------------------------------------------
# Router setup
# ---------------------------------------------------------------------------
router = APIRouter()

UPLOAD_DIR = "uploads"
MAX_VIDEO_BYTES = 200 * 1024 * 1024          # 200 MB hard limit
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm", ".jpg", ".jpeg", ".png", ".heic"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic"}

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Background pipeline wrapper
# Constructs MediaMetadata, runs the pipeline, and writes result to DB.
# Must be async — awaits DB calls after pipeline completes.
# ---------------------------------------------------------------------------
async def _run_pipeline_background(
    tracking_id: str,
    media_url_str: str,
    media_type: MediaType,
    geotag: str,
    caption: str,
    reporter_handle: str,
):
    media = MediaMetadata(
        media_url=media_url_str,          # pydantic coerces str → HttpUrl
        media_type=media_type,
        platform="app",                   # direct upload — no social platform
        posted_at=datetime.now(timezone.utc),
        geotag=geotag or None,
        caption=caption or None,
        reporter_handle=reporter_handle or None,
    )

    try:
        complaint = await run_complaint_pipeline(media)
        await update_status(tracking_id, complaint.status.value)
        await insert_log(
            tracking_id,
            f"Pipeline completed. Status: {complaint.status.value}. "
            f"Authority: {complaint.authority_name}.",
        )
    except Exception as exc:
        await update_status(tracking_id, "failed")
        await insert_log(tracking_id, f"Pipeline error: {exc}")


# ---------------------------------------------------------------------------
# POST /api/process
#
# Frontend sends:   FormData — video file, lat, lng
# Returns at once:  { "id": "CMP-XXXX", "status": "pending" }
# Pipeline runs in background via BackgroundTasks.
# ---------------------------------------------------------------------------
@router.post("/process", response_model=ProcessResponse)
async def process_video(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(default=None),
    video_url: str = Form(default=""),
    name: str = Form(default=""),
    email: str = Form(default=""),
    phone: str = Form(default=""),
    state: str = Form(...),
    district: str = Form(...),
    landmark: str = Form(default=""),
    user_issue_description: str = Form(default=""),
    user_id: str = Form(default="anonymous"),
):
    # -----------------------------------------------------------------------
    # Validate file type — check both MIME type and extension
    # MIME type alone is client-controlled and not trustworthy
    # -----------------------------------------------------------------------
    if not video and not video_url:
        pass  # media is optional — both absent is allowed
    if video and video_url:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or a video URL, not both."
        )
    
    if video:
        ext = os.path.splitext(video.filename or "video.mp4")[1].lower() or ".mp4"
        allowed_mime_prefixes = ("video/", "image/")
        if not any(video.content_type.startswith(p) for p in allowed_mime_prefixes) or ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Accepted formats: mp4, mov, avi, webm, jpg, png, heic. Got: {ext}"
            )

    # -----------------------------------------------------------------------
    # Generate tracking ID before anything else
    # Frontend needs this immediately; must exist even if later steps fail
    # -----------------------------------------------------------------------
    tracking_id = "CMP-" + uuid.uuid4().hex[:8].upper()

    # -----------------------------------------------------------------------
    # Write video to disk in chunks — avoids loading full file into RAM
    # FIX: was await video.read() which reads entire file into memory at once
    # -----------------------------------------------------------------------
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    abs_path = ""
    if video:
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        total_bytes = 0
        with open(filepath, "wb") as f:
            while chunk := await video.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_VIDEO_BYTES:
                    f.close()
                    os.remove(filepath)
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video exceeds {MAX_VIDEO_BYTES // (1024*1024)} MB limit."
                    )
                f.write(chunk)
        abs_path = os.path.abspath(filepath)
        print(f"[API] Saved video: {abs_path} ({total_bytes // 1024} KB)")

    # -----------------------------------------------------------------------
    # Create DB row immediately — prevents 404 on early status polls
    # FIX: was missing await (database.py is now async)
    # -----------------------------------------------------------------------
    await create_pending_complaint(
        tracking_id=tracking_id,
        user_id=user_id,
        video_path=abs_path if video else "",
        video_url=video_url,
        name=name,
        email=email,
        phone=phone,
        state=state,
        district=district,
    )

    # FIX: was missing await
    await insert_log(tracking_id, "Video uploaded successfully.")

    # -----------------------------------------------------------------------
    # Resolve the URL string and MediaType that the pipeline will consume.
    # Uploaded files are served from their absolute path (file:// scheme);
    # URL submissions are passed through directly.
    # -----------------------------------------------------------------------
    if video:
        media_url_str = f"file://{abs_path}"
        media_type = MediaType.IMAGE if ext in IMAGE_EXTENSIONS else MediaType.VIDEO
    else:
        media_url_str = video_url
        # Best-effort type detection for URL submissions
        url_ext = os.path.splitext(video_url.split("?")[0])[1].lower()
        media_type = MediaType.IMAGE if url_ext in IMAGE_EXTENSIONS else MediaType.VIDEO

    # Build a geotag string from the form fields the way the schema expects it
    geotag_parts = [p for p in (landmark, district, state) if p]
    geotag = ", ".join(geotag_parts) if geotag_parts else None

    # -----------------------------------------------------------------------
    # Fire background pipeline — returns immediately to frontend
    # -----------------------------------------------------------------------
    background_tasks.add_task(
        _run_pipeline_background,
        tracking_id=tracking_id,
        media_url_str=media_url_str,
        media_type=media_type,
        geotag=geotag,
        caption=user_issue_description,
        reporter_handle=user_id,
    )

    return JSONResponse(content={
        "id": tracking_id,
        "status": "pending"
    })


# ---------------------------------------------------------------------------
# GET /api/status/{tracking_id}
#
# Frontend polls this repeatedly while the pipeline runs.
# Returns: { "status": "detecting_issue", "logs": [...] }
#
# FIX: was def (sync) — DB calls are async, sync def never awaited them,
# so fetch_complaint() and fetch_logs() silently returned coroutine objects
# instead of executing. Converted to async def.
# ---------------------------------------------------------------------------
@router.get("/status/{tracking_id}", response_model=StatusResponse)
async def get_status(tracking_id: str):
    complaint = await fetch_complaint(tracking_id)

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Tracking ID not found."
        )

    logs = await fetch_logs(tracking_id)

    return JSONResponse(content={
        "status": complaint["submission_status"],
        "logs": logs
    })


# ---------------------------------------------------------------------------
# POST /api/confirm-location
#
# Frontend sends: { "id": "...", "final_lat": ..., "final_lng": ... }
# Returns:        { "status": "authority_mapped" }
#
# FIX 1: was def (sync) — same async issue as get_status above.
# FIX 2: confirmed lat/lng are now persisted to the complaints table
#         via update_location(). Previously only written to logs,
#         leaving lat/lng NULL in DB for authority mapping.
# ---------------------------------------------------------------------------
@router.post("/confirm-location", response_model=ConfirmLocationResponse)
async def confirm_location(data: ConfirmLocationRequest):
    complaint = await fetch_complaint(data.id)

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Tracking ID not found."
        )

    await update_location(
        tracking_id=data.id,
        state=data.final_state,
        district=data.final_district,
        landmark=data.final_landmark or "",
    )
    await insert_log(
        data.id,
        f"Location confirmed: {data.final_landmark or ''}, {data.final_district}, {data.final_state}".strip(", ")
    )

    await update_status(data.id, "authority_mapped")

    return JSONResponse(content={
        "status": "authority_mapped"
    })


# ---------------------------------------------------------------------------
# GET /api/complaint/{tracking_id}
# Full complaint detail — for complaint detail screen
# ---------------------------------------------------------------------------
@router.get("/complaint/{tracking_id}", response_model=ComplaintDetailResponse)
async def get_full_complaint(tracking_id: str):
    complaint = await fetch_complaint(tracking_id)

    if not complaint:
        raise HTTPException(
            status_code=404,
            detail="Complaint not found."
        )

    return JSONResponse(content=complaint)


# ---------------------------------------------------------------------------
# GET /api/complaints?user_id=xyz
# Complaint history list — for dashboard
# ---------------------------------------------------------------------------
@router.get("/complaints", response_model=ComplaintListResponse)
async def list_complaints(user_id: str = None):
    slim_list = await fetch_slim_complaints(user_id=user_id)

    return JSONResponse(content={
        "complaints": slim_list,
        "count": len(slim_list)
    })


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------
@router.get("/health")
def health():
    return {
        "status": "ok",
        "server": "Civic Engagement Backend"
    }
