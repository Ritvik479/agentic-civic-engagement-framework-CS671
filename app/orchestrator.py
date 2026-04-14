# app/orchestrator.py
# ---------------------------------------------------------------------------
# OWNED BY: Pair B
#
# UPDATED VERSION:
# - Accepts tracking_id from FastAPI route
# - Compatible with async background task architecture
# - Writes progress logs for frontend polling
# - Updates complaint status at every pipeline stage
# - No longer generates tracking ID internally
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
# Called asynchronously by FastAPI background task
# ---------------------------------------------------------------------------
def run_agent(
    video_path: str,
    tracking_id: str,
    user_location: str = "",
    user_id: str = "anonymous"
):
    """
    Runs full complaint pipeline asynchronously.

    Args:
        video_path    : absolute path to uploaded video
        tracking_id   : generated in API route before pipeline starts
        user_location : lat,lng string from frontend
        user_id       : uploader identifier
    """

    # -----------------------------------------------------------------------
    # Create complaint context object
    # -----------------------------------------------------------------------
    ctx = ComplaintContext(
        tracking_id=tracking_id,
        user_id=user_id,
        video_path=video_path
    )

    print(f"\n{'='*60}")
    print("[Orchestrator] Pipeline started")
    print(f"[Tracking ID] {tracking_id}")
    print(f"[Video]       {video_path}")
    print(f"[Location]    {user_location}")
    print(f"{'='*60}")

    try:

        # ================================================================
        # STEP 1 — Pair D: Vision + Speech
        # ================================================================
        update_status(tracking_id, "detecting_issue")
        insert_log(tracking_id, "Issue detection started.")

        print("\n[Step 1] Running vision + speech agent...")

        pair_d_result = detect_issue_and_location(
            video_path=video_path,
            user_location=user_location
        )

        ctx.issue_type = pair_d_result["issue_type"]
        ctx.location = pair_d_result["location"]
        ctx.severity = pair_d_result["severity"]
        ctx.transcript = pair_d_result["transcript"]

        save_complaint(ctx)

        insert_log(
            tracking_id,
            f"Issue detected: {ctx.issue_type} at {ctx.location}"
        )

        print(
            f"[Step 1 Complete] {ctx.issue_type} | "
            f"{ctx.location} | severity {ctx.severity}/5"
        )

        # ================================================================
        # STEP 2 — Trio C: Authority Mapping
        # ================================================================
        update_status(tracking_id, "mapping_authority")
        insert_log(tracking_id, "Authority mapping started.")

        print("\n[Step 2] Looking up authority...")

        authority = lookup_authority(
            ctx.issue_type,
            ctx.location
        )

        ctx.authority_name = authority["authority_name"]
        ctx.authority_email = authority["authority_email"]
        ctx.authority_portal = authority["authority_portal"]

        save_complaint(ctx)

        insert_log(
            tracking_id,
            f"Authority mapped: {ctx.authority_name}"
        )

        print(f"[Step 2 Complete] {ctx.authority_name}")

        # ================================================================
        # STEP 3 — Trio C: Complaint Drafting
        # ================================================================
        update_status(tracking_id, "drafting_complaint")
        insert_log(tracking_id, "Complaint drafting started.")

        print("\n[Step 3] Drafting complaint...")

        ctx.complaint_text = draft_complaint(asdict(ctx))

        save_complaint(ctx)

        insert_log(
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
        update_status(tracking_id, "submitting")
        insert_log(tracking_id, "Portal submission started.")

        print("\n[Step 4] Submitting complaint...")

        submission = submit_complaint(asdict(ctx))

        ctx.submission_status = submission["submission_status"]
        ctx.submission_screenshot = submission["submission_screenshot"]

        save_complaint(ctx)

        insert_log(
            tracking_id,
            f"Submission result: {ctx.submission_status}"
        )

        print(
            f"[Step 4 Complete] Submission status: "
            f"{ctx.submission_status}"
        )

        # ================================================================
        # STEP 5 — Final Success State
        # ================================================================
        if ctx.submission_status == "submitted":
            update_status(tracking_id, "submitted")
            insert_log(tracking_id, "Complaint submitted successfully.")
        else:
            update_status(tracking_id, "failed")
            insert_log(tracking_id, "Complaint submission failed.")

    except Exception as e:
        # ================================================================
        # Failure Handling
        # ================================================================
        ctx.error = str(e)
        ctx.submission_status = "failed"

        save_complaint(ctx)
        update_status(tracking_id, "failed")
        insert_log(tracking_id, f"Pipeline failed: {str(e)}")

        print(f"\n[Orchestrator ERROR] {e}")
        traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"[Pipeline Complete] Final status: {ctx.submission_status}")
    print(f"{'='*60}\n")