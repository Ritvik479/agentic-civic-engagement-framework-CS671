# app/orchestrator.py
# ---------------------------------------------------------------------------
# OWNED BY: Pair B
#
# Changes from v1:
# - run_agent converted to async def — all DB calls now awaited
# - Signature changed from user_location: str to user_lat/user_lng: float
#   to match api.py and context.py
# - ctx.location replaced with ctx.lat, ctx.lng, ctx.location_label
#   throughout (context.py no longer has a location field)
# - user_lat/user_lng written to ctx immediately after creation,
#   so frontend-supplied coordinates are available as fallback if
#   Pair D's vision agent cannot extract location from video
# - lookup_authority now receives lat/lng floats instead of location string
# ---------------------------------------------------------------------------

import traceback
from dataclasses import asdict

from app.context import ComplaintContext

from app.db.database import (
    save_complaint,
    insert_log,
    update_status
)

from app.agents.vision_speech_agent import detect_issue_and_location
from app.agents.authority_llm_agent import lookup_authority, draft_complaint
from app.agents.submission_agent import submit_complaint


# ---------------------------------------------------------------------------
# Main pipeline runner
# Called asynchronously by FastAPI BackgroundTasks
# ---------------------------------------------------------------------------
async def run_agent(
    video_path: str,
    tracking_id: str,
    user_lat: float = 0.0,      # FIX: was user_location: str — must match api.py
    user_lng: float = 0.0,
    user_id: str = "anonymous"
):
    """
    Runs full complaint pipeline as an async background task.

    Args:
        video_path  : absolute path to uploaded video
        tracking_id : generated in api.py before pipeline starts
        user_lat    : latitude from frontend FormData
        user_lng    : longitude from frontend FormData
        user_id     : uploader identifier
    """

    # -----------------------------------------------------------------------
    # Create complaint context object
    # -----------------------------------------------------------------------
    ctx = ComplaintContext(
        tracking_id=tracking_id,
        user_id=user_id,
        video_path=video_path
    )

    # FIX: write frontend-supplied coordinates immediately so they're
    # available as fallback if Pair D cannot extract location from video
    ctx.lat = user_lat
    ctx.lng = user_lng

    print(f"\n{'='*60}")
    print("[Orchestrator] Pipeline started")
    print(f"[Tracking ID] {tracking_id}")
    print(f"[Video]       {video_path}")
    print(f"[Location]    {user_lat}, {user_lng}")
    print(f"{'='*60}")

    try:

        # ================================================================
        # STEP 1 — Pair D: Vision + Speech
        # Expects pair_d_result to contain:
        #   issue_type: str
        #   lat: float  (may be None if agent can't detect location)
        #   lng: float
        #   location_label: str  (e.g. "Shimla, HP")
        #   severity: int (0–5)
        #   transcript: str
        # ================================================================
        await update_status(tracking_id, "detecting_issue")
        await insert_log(tracking_id, "Issue detection started.")

        print("\n[Step 1] Running vision + speech agent...")

        pair_d_result = detect_issue_and_location(
            video_path=video_path,
            user_lat=user_lat,
            user_lng=user_lng
        )

        ctx.issue_type = pair_d_result["issue_type"]
        ctx.severity   = pair_d_result["severity"]
        ctx.transcript = pair_d_result["transcript"]

        # FIX: ctx.location no longer exists — use lat/lng/location_label
        # Only overwrite frontend coordinates if Pair D found better ones
        if pair_d_result.get("lat") is not None:
            ctx.lat = pair_d_result["lat"]
        if pair_d_result.get("lng") is not None:
            ctx.lng = pair_d_result["lng"]
        ctx.location_label = pair_d_result.get("location_label", "")

        await save_complaint(ctx)
        await insert_log(
            tracking_id,
            f"Issue detected: {ctx.issue_type} at {ctx.location_label or f'({ctx.lat}, {ctx.lng})'}"
        )

        print(
            f"[Step 1 Complete] {ctx.issue_type} | "
            f"{ctx.location_label} | severity {ctx.severity}/5"
        )

        # ================================================================
        # STEP 2 — Trio C: Authority Mapping
        # FIX: pass lat/lng floats instead of ctx.location string
        # Flag to Trio C: lookup_authority signature must accept
        # issue_type, lat, lng instead of issue_type, location
        # ================================================================
        await update_status(tracking_id, "mapping_authority")
        await insert_log(tracking_id, "Authority mapping started.")

        print("\n[Step 2] Looking up authority...")

        authority = lookup_authority(
            ctx.issue_type,
            ctx.lat,
            ctx.lng
        )

        ctx.authority_name   = authority["authority_name"]
        ctx.authority_email  = authority["authority_email"]
        ctx.authority_portal = authority["authority_portal"]

        await save_complaint(ctx)
        await insert_log(
            tracking_id,
            f"Authority mapped: {ctx.authority_name}"
        )

        print(f"[Step 2 Complete] {ctx.authority_name}")

        # ================================================================
        # STEP 3 — Trio C: Complaint Drafting
        # ================================================================
        await update_status(tracking_id, "drafting_complaint")
        await insert_log(tracking_id, "Complaint drafting started.")

        print("\n[Step 3] Drafting complaint...")

        ctx.complaint_text = draft_complaint(asdict(ctx))

        await save_complaint(ctx)
        await insert_log(
            tracking_id,
            "Complaint draft generated successfully."
        )

        print(
            f"[Step 3 Complete] Draft length: "
            f"{len(ctx.complaint_text)} chars"
        )

        # ================================================================
        # STEP 4 — Pair E: Portal Submission
        # ================================================================
        await update_status(tracking_id, "submitting")
        await insert_log(tracking_id, "Portal submission started.")

        print("\n[Step 4] Submitting complaint...")

        submission = submit_complaint(asdict(ctx))

        ctx.submission_status     = submission["submission_status"]
        ctx.submission_screenshot = submission["submission_screenshot"]

        await save_complaint(ctx)
        await insert_log(
            tracking_id,
            f"Submission result: {ctx.submission_status}"
        )

        print(
            f"[Step 4 Complete] Submission status: "
            f"{ctx.submission_status}"
        )

        # ================================================================
        # STEP 5 — Final Status
        # ================================================================
        if ctx.submission_status == "submitted":
            await update_status(tracking_id, "submitted")
            await insert_log(tracking_id, "Complaint submitted successfully.")
        else:
            await update_status(tracking_id, "failed")
            await insert_log(tracking_id, "Complaint submission failed.")

    except Exception as e:
        # ================================================================
        # Failure Handling — always write terminal state so frontend
        # stops polling and shows an error instead of hanging
        # ================================================================
        ctx.error = str(e)
        ctx.submission_status = "failed"

        await save_complaint(ctx)
        await update_status(tracking_id, "failed")
        await insert_log(tracking_id, f"Pipeline failed: {str(e)}")

        print(f"\n[Orchestrator ERROR] {e}")
        traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"[Pipeline Complete] Final status: {ctx.submission_status}")
    print(f"{'='*60}\n")