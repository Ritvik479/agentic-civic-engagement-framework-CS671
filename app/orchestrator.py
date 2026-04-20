# app/orchestrator.py

import asyncio
from dataclasses import asdict

from app.context import ComplaintContext
from app.db.database import (
    save_complaint,
    update_status,
    insert_log,
    fetch_complaint,
)
from app.tools.pair_d.vision_pipeline_tool  import run_vision_pipeline
from app.tools.trio_c.authority_lookup_tool import lookup_authority
from app.tools.trio_c.severity_score_tool   import calculate_severity
from app.tools.trio_c.complaint_draft_tool  import draft_complaint
from app.tools.pair_b.submission_agent_tool import submit_complaint

# How often to poll DB for location confirmation (seconds)
LOCATION_POLL_INTERVAL = 5
# Maximum time to wait for user to confirm location before giving up (seconds)
LOCATION_POLL_TIMEOUT  = 600   # 10 minutes


async def run_agent(
    video_path:             str,
    video_url:              str,
    tracking_id:            str,
    name:                   str,
    email:                  str,
    phone:                  str,
    user_state:             str,
    user_district:          str,
    landmark:               str,
    user_issue_description: str,
    user_id:                str,
):
    """
    Full async pipeline: vision → location confirmation (if needed)
    → authority lookup → severity → complaint draft → submission.

    Called by FastAPI BackgroundTasks — must never raise.
    All failures are caught, logged, and written to DB as status="failed".
    """

    # ── 1. Build initial context ────────────────────────────────────────────
    user_location = ", ".join(p for p in [landmark, user_district, user_state] if p)

    ctx = ComplaintContext(
        tracking_id             = tracking_id,
        user_id                 = user_id,
        video_path              = video_path,
        video_url               = video_url,
        name                    = name,
        email                   = email,
        phone                   = phone,
        user_issue_description  = user_issue_description,
        landmark                = landmark,
        state                   = user_state,
        district                = user_district,
        location_label          = user_location,
    )

    try:

        # ── 2. Vision pipeline (Pair D) ─────────────────────────────────────
        await _log(tracking_id, "Starting vision analysis...")
        await update_status(tracking_id, "detecting_issue")
        ctx.submission_status = "detecting_issue"

        vision_result = await asyncio.to_thread(
            run_vision_pipeline,
            video_path    = video_path or None,
            url           = video_url  or None,
            user_location = user_location,
            whatsapp_text = "",
        )

        ctx.issue_type     = vision_result.get("issue_type", "Unknown")
        ctx.transcript     = vision_result.get("transcript", "")
        ctx.state          = vision_result.get("state")     or user_state
        ctx.district       = vision_result.get("district")  if vision_result.get("district") != vision_result.get("location_label") else user_district
        ctx.location_label = vision_result.get("location_label") or user_location

        await save_complaint(ctx)
        await _log(tracking_id, f"Issue detected: {ctx.issue_type} at {ctx.location_label}.")

        # ── 3. Location confirmation gate ───────────────────────────────────
        if vision_result.get("needs_user_input"):
            await update_status(tracking_id, "needs_location")
            await _log(tracking_id, "Location unclear — please confirm your location.")

            confirmed = await _wait_for_location(tracking_id)

            if not confirmed:
                # Timed out — fall back to user-supplied state/district
                await _log(
                    tracking_id,
                    "Location confirmation timed out — using submitted location as fallback."
                )
                # ctx.state and ctx.district already set from user_state/user_district above
            else:
                # Re-fetch confirmed location from DB (written by /confirm-location)
                refreshed = await fetch_complaint(tracking_id)
                if refreshed:
                    ctx.state          = refreshed.get("state")          or ctx.state
                    ctx.district       = refreshed.get("district")        or ctx.district
                    ctx.landmark       = refreshed.get("landmark")        or ctx.landmark
                    ctx.location_label = refreshed.get("location_label")  or ctx.location_label

                await _log(tracking_id, f"Location confirmed: {ctx.location_label}.")

        # ── 4. Authority lookup ─────────────────────────────────────────────
        await update_status(tracking_id, "mapping_authority")
        ctx.submission_status = "mapping_authority"
        await _log(tracking_id, "Mapping to relevant authority...")

        authority = lookup_authority(
            issue    = ctx.issue_type,
            state    = ctx.state,
            district = ctx.district,
            severity = ctx.severity or 2,   # severity not yet scored — use default
        )

        ctx.authority_name      = authority.get("authority_name", "")
        ctx.authority_email     = authority.get("authority_email", "")
        ctx.authority_portal    = authority.get("authority_portal", "")
        ctx.authority_phone     = authority.get("authority_phone", "")
        ctx.authority_level     = authority.get("current_level", "level1")
        ctx.authority_level_num = authority.get("current_level_num", 1)

        await save_complaint(ctx)
        await _log(tracking_id, f"Authority mapped: {ctx.authority_name}.")

        # ── 5. Severity scoring ─────────────────────────────────────────────
        await _log(tracking_id, "Scoring complaint severity...")

        description = _build_description(ctx)
        severity_result = await asyncio.to_thread(
            calculate_severity,
            issue       = ctx.issue_type,
            description = description,
            location    = ctx.location_label,
        )

        ctx.severity = severity_result.get("severity", 2)
        if not severity_result.get("success"):
            await _log(tracking_id, "Severity scoring failed — defaulting to 2.")
        else:
            await _log(tracking_id, f"Severity scored: {ctx.severity}/5.")

        # Re-run authority lookup now that we have real severity
        # (severity affects which level authority is assigned)
        authority = lookup_authority(
            issue    = ctx.issue_type,
            state    = ctx.state,
            district = ctx.district,
            severity = ctx.severity,
        )
        ctx.authority_name      = authority.get("authority_name", "")
        ctx.authority_email     = authority.get("authority_email", "")
        ctx.authority_portal    = authority.get("authority_portal", "")
        ctx.authority_phone     = authority.get("authority_phone", "")
        ctx.authority_level     = authority.get("current_level", "level1")
        ctx.authority_level_num = authority.get("current_level_num", 1)

        await save_complaint(ctx)
        await _log(tracking_id, f"Authority confirmed post-severity: {ctx.authority_name}.")

        # ── 6. Complaint drafting ───────────────────────────────────────────
        await update_status(tracking_id, "drafting_complaint")
        ctx.submission_status = "drafting_complaint"
        await _log(tracking_id, "Drafting formal complaint...")

        complaint_text = await asyncio.to_thread(
            draft_complaint,
            issue       = ctx.issue_type,
            description = description,
            location    = ctx.location_label,
        )

        if complaint_text.startswith("Failed") or complaint_text.startswith("Unable"):
            await _log(tracking_id, f"Complaint draft issue: {complaint_text}")
            # Non-fatal — proceed with whatever text was returned
            # The sentinel strings are still valid fallback complaint text

        ctx.complaint_text = complaint_text
        await save_complaint(ctx)
        await _log(tracking_id, "Complaint drafted.")

        # ── 7. Multi-channel submission (Pair B) ────────────────────────────
        await update_status(tracking_id, "submitting")
        ctx.submission_status = "drafting_complaint"
        await _log(tracking_id, "Submitting complaint via portal, email, and WhatsApp...")

        submission = await asyncio.to_thread(submit_complaint, asdict(ctx))

        ctx.submission_status     = submission.get("submission_status", "failed")
        ctx.submission_screenshot = submission.get("submission_screenshot", "")
        ctx.complaint_ref_id      = submission.get("complaint_ref_id", "")

        await save_complaint(ctx)
        await update_status(tracking_id, ctx.submission_status)

        if submission.get("success"):
            await _log(
                tracking_id,
                f"Complaint submitted successfully. "
                f"Ref: {ctx.complaint_ref_id}. "
                f"Status: {ctx.submission_status}."
            )
        else:
            await _log(
                tracking_id,
                f"Submission completed with status: {ctx.submission_status}. "
                f"Error: {submission.get('error', '')}."
            )

    except Exception as e:
        # Catch-all — pipeline must never crash silently
        import traceback
        traceback.print_exc()
        ctx.error = str(e)
        ctx.submission_status = "failed"
        try:
            await save_complaint(ctx)
            await update_status(tracking_id, "failed")
            await _log(tracking_id, f"Pipeline failed: {e}")
        except Exception as inner:
            print(f"[Orchestrator] CRITICAL: could not write failure to DB: {inner}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _wait_for_location(tracking_id: str) -> bool:
    """
    Polls DB until /confirm-location flips status to 'authority_mapped',
    or until LOCATION_POLL_TIMEOUT seconds elapse.
    Returns True if confirmed, False if timed out.
    """
    elapsed = 0
    while elapsed < LOCATION_POLL_TIMEOUT:
        await asyncio.sleep(LOCATION_POLL_INTERVAL)
        elapsed += LOCATION_POLL_INTERVAL
        row = await fetch_complaint(tracking_id)
        if row and row.get("submission_status") == "authority_mapped":
            return True
    return False


async def _log(tracking_id: str, message: str):
    """Thin wrapper — keeps pipeline body readable."""
    print(f"[Orchestrator:{tracking_id}] {message}")
    await insert_log(tracking_id, message)


def _build_description(ctx: ComplaintContext) -> str:
    """
    Assembles the best available description for severity scoring and
    complaint drafting from transcript and user-supplied text.
    Transcript is preferred — it's richer. User description appended
    as supplementary context if present.
    """
    parts = []
    if ctx.transcript:
        parts.append(ctx.transcript)
    if ctx.user_issue_description:
        parts.append(f"Additional context: {ctx.user_issue_description}")
    return " ".join(parts) or ctx.issue_type