# app/orchestrator.py
# ---------------------------------------------------------------------------
# OWNED BY: Pair B
# ---------------------------------------------------------------------------

import traceback
from dataclasses import asdict

from app.context import ComplaintContext

from app.db.database import (
    save_complaint,
    insert_log,
    update_status
)

# ---------------------------------------------------------------------------
# Correct tool imports
# ---------------------------------------------------------------------------

# Pair D tools
from app.tools.pair_d.vision import detect_issue_and_location

# Trio C tools
from app.tools.trio_c.authority_lookup_tool import lookup_authority
from app.tools.trio_c.severity_score_tool import calculate_severity
from app.tools.trio_c.complaint_draft_tool import draft_complaint

# Pair B tools
from app.tools.pair_b.submission_agent import submit_complaint


# ---------------------------------------------------------------------------
# Main pipeline runner
# Called asynchronously by FastAPI BackgroundTasks
# ---------------------------------------------------------------------------
async def run_agent(
    video_path: str,
    tracking_id: str,
    user_state: str = "",
    user_district: str = "",
    user_id: str = "anonymous"
):
    """
    Runs full complaint pipeline as an async background task.
    """

    # -----------------------------------------------------------------------
    # Create complaint context object
    # -----------------------------------------------------------------------
    ctx = ComplaintContext(
        tracking_id=tracking_id,
        user_id=user_id,
        video_path=video_path
    )

    ctx.state = user_state
    ctx.district = user_district

    print(f"\n{'='*60}")
    print("[Orchestrator] Pipeline started")
    print(f"[Tracking ID] {tracking_id}")
    print(f"[Video]       {video_path}")
    print(f"[Location]    {user_district}, {user_state}")
    print(f"{'='*60}")

    try:

        # ================================================================
        # STEP 1 — Pair D: Vision + Speech
        # ================================================================
        await update_status(tracking_id, "detecting_issue")
        await insert_log(tracking_id, "Issue detection started.")

        print("\n[Step 1] Running vision + speech agent...")

        pair_d_result = detect_issue_and_location(
            video_path=video_path,
            user_state=user_state,
            user_district=user_district
        )

        ctx.issue_type = pair_d_result["issue_type"]
        ctx.transcript = pair_d_result["transcript"]

        if pair_d_result.get("state"):
            ctx.state = pair_d_result["state"]
        if pair_d_result.get("district"):
            ctx.district = pair_d_result["district"]

        ctx.location_label = pair_d_result.get("location_label", "")

        # ================================================================
        # STEP 1.5 — Trio C: Severity Scoring
        # ================================================================
        await insert_log(tracking_id, "Severity scoring started.")

        print("\n[Step 1.5] Calculating severity...")

        severity_result = await calculate_severity(
            issue=ctx.issue_type,
            description=ctx.transcript,
            location=ctx.location_label or f"{ctx.district}, {ctx.state}"
        )

        ctx.severity = severity_result["severity"]

        await save_complaint(ctx)

        await insert_log(
            tracking_id,
            f"Issue detected: {ctx.issue_type} at "
            f"{ctx.location_label or f'{ctx.district}, {ctx.state}'} | "
            f"Severity {ctx.severity}/5"
        )

        print(
            f"[Step 1 Complete] {ctx.issue_type} | "
            f"{ctx.location_label} | severity {ctx.severity}/5"
        )

        # ================================================================
        # STEP 2 — Trio C: Authority Mapping
        # ================================================================
        await update_status(tracking_id, "mapping_authority")
        await insert_log(tracking_id, "Authority mapping started.")

        print("\n[Step 2] Looking up authority...")

        authority = lookup_authority(
            ctx.issue_type,
            ctx.state,
            ctx.district,
            ctx.severity
        )

        ctx.authority_name = authority["authority_name"]
        ctx.authority_email = authority["authority_email"]
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
        # STEP 4 — Pair B: Portal Submission
        # ================================================================
        await update_status(tracking_id, "submitting")
        await insert_log(tracking_id, "Portal submission started.")

        print("\n[Step 4] Submitting complaint...")

        submission = submit_complaint(asdict(ctx))

        ctx.submission_status = submission["submission_status"]
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
            await insert_log(
                tracking_id,
                "Complaint submitted successfully."
            )
        else:
            await update_status(tracking_id, "failed")
            await insert_log(
                tracking_id,
                "Complaint submission failed."
            )

    except Exception as e:
        # ================================================================
        # Failure Handling
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