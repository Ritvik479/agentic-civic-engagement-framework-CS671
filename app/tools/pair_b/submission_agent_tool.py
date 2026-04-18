"""
app/tools/pair_b/submission_agent.py
-------------------------------------
Agent 5 — Submission coordinator.

Orchestrates the three dispatch tools in sequence:
    1. portal_navigator_tool  — Playwright form fill → complaint_ref_id
    2. email_dispatch_tool    — formal email to authority
    3. whatsapp_dispatch_tool — WhatsApp alert (secondary, never blocks)

Computes a unified submission_status from the results and returns a single
clean dict to the orchestrator.

submission_status values:
    "submitted"   — portal succeeded (email/WhatsApp are best-effort)
    "email_only"  — portal failed, email succeeded
    "failed"      — both portal and email failed

WhatsApp result never affects submission_status — it is always best-effort.

Design:
- Sync function (tools are sync, orchestrator is async — team design choice)
- Returns plain dict matching team tool contract
- Each tool's result is preserved in full for logging/debugging
"""

from app.tools.pair_b.portal_navigator_tool import submit_to_portal
from app.tools.pair_b.email_dispatch_tool   import send_complaint_email
from app.tools.pair_b.whatsapp_dispatch_tool import send_whatsapp_message


# ---------------------------------------------------------------------------
# Public coordinator function
# ---------------------------------------------------------------------------

def submit_complaint(ctx: dict) -> dict:
    """
    Runs all three dispatch tools and returns an aggregated result.

    Args:
        ctx: Full complaint context dict (from dataclasses.asdict(ctx)).

    Returns:
        {
            "submission_status":     str,   # "submitted" | "email_only" | "failed"
            "submission_screenshot": str,   # file path from portal navigator, or ""
            "complaint_ref_id":      str,   # portal-assigned ref, or ""
            "portal_result":         dict,  # raw result from portal_navigator_tool
            "email_result":          dict,  # raw result from email_dispatch_tool
            "whatsapp_result":       dict,  # raw result from whatsapp_dispatch_tool
            "success":               bool,
            "error":                 str    # "" on success
        }
    """

    print("\n[SubmissionAgent] Starting multi-channel dispatch...")
    print(f"  Tracking ID:    {ctx.get('tracking_id', 'N/A')}")
    print(f"  Authority:      {ctx.get('authority_name', 'N/A')}")
    print(f"  Portal URL:     {ctx.get('authority_portal', 'N/A')}")
    print(f"  Authority Email:{ctx.get('authority_email', 'N/A')}")

    # ── Channel 1: Portal (Playwright) ──────────────────────────────────────
    print("\n[SubmissionAgent] [1/3] Portal submission...")
    portal_result = submit_to_portal(ctx)

    if portal_result["success"]:
        print(
            f"[SubmissionAgent] Portal ✓ | "
            f"Ref: {portal_result['complaint_ref_id']}"
        )
    else:
        print(f"[SubmissionAgent] Portal ✗ | {portal_result['error']}")

    # ── Channel 2: Email ────────────────────────────────────────────────────
    # Pass an enriched ctx with complaint_ref_id from portal if available,
    # so the email body can reference it
    email_ctx = _enrich_ctx(ctx, portal_result)

    print("\n[SubmissionAgent] [2/3] Email dispatch...")
    email_result = send_complaint_email(email_ctx)

    if email_result["success"]:
        mock_tag = " (mocked)" if email_result.get("mocked") else ""
        print(f"[SubmissionAgent] Email ✓{mock_tag}")
    else:
        print(f"[SubmissionAgent] Email ✗ | {email_result['error']}")

    # ── Channel 3: WhatsApp (best-effort, never blocks) ─────────────────────
    print("\n[SubmissionAgent] [3/3] WhatsApp dispatch...")
    whatsapp_result = send_whatsapp_message(email_ctx)

    channel = whatsapp_result.get("channel", "unknown")
    if channel == "skipped":
        print("[SubmissionAgent] WhatsApp — skipped (no number available)")
    elif whatsapp_result["success"]:
        mock_tag = " (mocked)" if whatsapp_result.get("mocked") else ""
        print(f"[SubmissionAgent] WhatsApp ✓{mock_tag}")
    else:
        # WhatsApp failure is logged but does not affect submission_status
        print(f"[SubmissionAgent] WhatsApp ✗ | {whatsapp_result['error']} — non-blocking")

    # ── Aggregate status ─────────────────────────────────────────────────────
    submission_status = _compute_status(portal_result, email_result)

    screenshot = portal_result.get("submission_screenshot", "")
    complaint_ref = portal_result.get("complaint_ref_id", "")
    overall_ok    = submission_status != "failed"

    # Build summary error string for failed cases
    error_summary = ""
    if not overall_ok:
        errors = []
        if not portal_result["success"]:
            errors.append(f"Portal: {portal_result['error']}")
        if not email_result["success"]:
            errors.append(f"Email: {email_result['error']}")
        error_summary = " | ".join(errors)

    print(f"\n[SubmissionAgent] Final status: {submission_status.upper()}")
    if error_summary:
        print(f"[SubmissionAgent] Errors: {error_summary}")

    return {
        "submission_status":     submission_status,
        "submission_screenshot": screenshot,
        "complaint_ref_id":      complaint_ref,
        "portal_result":         portal_result,
        "email_result":          email_result,
        "whatsapp_result":       whatsapp_result,
        "success":               overall_ok,
        "error":                 error_summary
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _enrich_ctx(ctx: dict, portal_result: dict) -> dict:
    """
    Returns a shallow copy of ctx with complaint_ref_id injected from the
    portal result, so email and WhatsApp bodies can reference it.
    Does not mutate the original ctx dict.
    """
    enriched = dict(ctx)
    ref = portal_result.get("complaint_ref_id", "")
    if ref:
        enriched["complaint_ref_id"] = ref
    return enriched


def _compute_status(portal_result: dict, email_result: dict) -> str:
    """
    Derives submission_status from portal and email results.

    Rules:
        portal success                        → "submitted"
        portal fail + email success           → "email_only"
        portal fail + email fail              → "failed"

    WhatsApp is deliberately excluded from this logic — it is always
    best-effort and its failure should never degrade the status.
    """
    if portal_result["success"] and portal_result.get("complaint_ref_id"):
        return "submitted"

    if email_result["success"]:
        return "email_only"

    return "failed"