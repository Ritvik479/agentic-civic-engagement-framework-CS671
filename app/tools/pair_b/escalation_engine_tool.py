"""
app/tools/pair_b/escalation_engine_tool.py
-------------------------------------------
Agent 6 — Escalation engine.

Runs as a scheduler-driven background process (via APScheduler in main.py).
NOT called by the orchestrator directly.

Responsibilities:
    1. Poll DB for complaints that have breached their SLA
    2. Identify the next escalation level from authority_data.json
    3. Update authority fields in DB to the next level
    4. Re-submit complaint via submission_agent.submit_complaint()
    5. Log every escalation action to complaint_logs

SLA thresholds (hours before escalation, keyed by severity):
    severity 1 → 72h
    severity 2 → 48h
    severity 3 → 24h
    severity 4 → 12h

Effective complaint age is read from the dummy portal's per-complaint
clock offset via GET /api/complaint/<ref_id>, so time simulation works
transparently — this tool never needs to know the clock is fake.

Statuses this tool acts on:
    "submitted"           → check SLA, escalate if breached
    "email_only"          → check SLA, escalate if breached (portal failed before)
    "escalated_l2"        → check SLA at level 2, escalate to l3 if needed
    "escalated_l3"        → check SLA at level 3, escalate to l4 if needed
    "escalated_l4"        → already at top — log warning, no further escalation

Statuses this tool never touches:
    "pending"             → still being processed by pipeline
    "detecting_issue"     → still being processed
    "mapping_authority"   → still being processed
    "drafting_complaint"  → still being processed
    "submitting"          → still being processed
    "failed"              → pipeline failed, not an escalation concern
    "resolved"            → closed by admin, stop tracking

Design:
- run_escalation_check() is sync (called by APScheduler)
- DB calls inside are run via asyncio.run() since database.py is async
- Returns plain dict summary for logging
"""

import os
import json
import asyncio
import datetime
import urllib.request
import urllib.error
import traceback
from dataclasses import asdict

from app.context import ComplaintContext
from app.db.database import (
    fetch_slim_complaints,
    fetch_complaint,
    update_status,
    insert_log,
    save_complaint,
)
from app.tools.pair_b.submission_agent_tool import submit_complaint

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

AUTHORITY_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "configs", "authority_data.json"
)

DUMMY_PORTAL_URL = os.getenv("DUMMY_PORTAL_URL", "http://localhost:5050")

# Severity → SLA in hours before escalation is triggered
SLA_HOURS: dict[int, int] = {
    1: 72,
    2: 48,
    3: 24,
    4: 12,
}
DEFAULT_SLA_HOURS = 48  # fallback if severity missing or unexpected

# Statuses that are eligible for escalation checks
ESCALATABLE_STATUSES = {
    "submitted",
    "email_only",
    "escalated_l2",
    "escalated_l3",
}

# Status that means we've hit the ceiling — log and stop
CEILING_STATUS = "escalated_l4"

# Statuses that mean the complaint is closed or in-flight — never touch
IGNORED_STATUSES = {
    "pending", "detecting_issue", "mapping_authority",
    "drafting_complaint", "submitting", "failed", "resolved",
}

# Map current status → current level number (for authority lookup)
STATUS_TO_LEVEL: dict[str, int] = {
    "submitted":    1,
    "email_only":   1,
    "escalated_l2": 2,
    "escalated_l3": 3,
    "escalated_l4": 4,
}

# Map level number → next level number and new status string
ESCALATION_LADDER: dict[int, tuple[int, str]] = {
    1: (2, "escalated_l2"),
    2: (3, "escalated_l3"),
    3: (4, "escalated_l4"),
}

# ---------------------------------------------------------------------------
# Authority data — loaded once at module import
# ---------------------------------------------------------------------------

def _load_authority_data() -> list[dict]:
    try:
        with open(AUTHORITY_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)["data"]
    except Exception as e:
        print(f"[EscalationEngine] WARNING: Could not load authority_data.json: {e}")
        return []

_AUTHORITY_DATA: list[dict] = _load_authority_data()

# Build lookup index: (state, district, issue) → entry
_AUTHORITY_INDEX: dict[tuple, dict] = {
    (
        entry["state"].strip().lower(),
        entry["district"].strip().lower(),
        entry["issue"].strip().lower(),
    ): entry
    for entry in _AUTHORITY_DATA
}


# ---------------------------------------------------------------------------
# Public entry point — called by APScheduler
# ---------------------------------------------------------------------------

def run_escalation_check() -> dict:
    """
    Main scheduler entry point. Checks all escalatable complaints and
    escalates any that have breached their SLA.

    Returns a summary dict for logging:
        {
            "checked":   int,   # complaints evaluated
            "escalated": int,   # complaints escalated this run
            "skipped":   int,   # within SLA, no action needed
            "errors":    list   # list of error strings
        }
    """
    print(f"\n{'='*55}")
    print(f"[EscalationEngine] Check started — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*55}")

    summary = {"checked": 0, "escalated": 0, "skipped": 0, "errors": []}

    # Fetch all complaints that could need escalation
    try:
        all_complaints = asyncio.run(fetch_slim_complaints())
    except Exception as e:
        msg = f"DB fetch failed: {e}"
        print(f"[EscalationEngine] ERROR: {msg}")
        summary["errors"].append(msg)
        return summary

    escalatable = [
        c for c in all_complaints
        if c.get("submission_status") in ESCALATABLE_STATUSES
    ]

    print(f"[EscalationEngine] {len(escalatable)} complaint(s) eligible for check.")

    for slim in escalatable:
        tracking_id = slim["tracking_id"]
        try:
            _process_complaint(tracking_id, slim, summary)
        except Exception as e:
            msg = f"{tracking_id}: unhandled error — {e}"
            print(f"[EscalationEngine] ERROR: {msg}")
            traceback.print_exc()
            summary["errors"].append(msg)

    print(
        f"\n[EscalationEngine] Run complete — "
        f"checked: {summary['checked']}, "
        f"escalated: {summary['escalated']}, "
        f"skipped: {summary['skipped']}, "
        f"errors: {len(summary['errors'])}"
    )
    return summary


# ---------------------------------------------------------------------------
# Per-complaint processing
# ---------------------------------------------------------------------------

def _process_complaint(tracking_id: str, slim: dict, summary: dict):
    """Evaluates one complaint and escalates if SLA is breached."""

    summary["checked"] += 1
    status   = slim.get("submission_status", "")
    severity = slim.get("severity") or 2

    # ── Already at ceiling ───────────────────────────────────────────────────
    if status == CEILING_STATUS:
        print(f"[EscalationEngine] {tracking_id}: at level 4 ceiling — no further escalation.")
        summary["skipped"] += 1
        return

    # ── Get effective complaint age ──────────────────────────────────────────
    # First try the dummy portal API (respects per-complaint clock offset).
    # Fall back to computing age from DB submitted_at if portal unreachable.
    complaint_full = asyncio.run(fetch_complaint(tracking_id))
    if not complaint_full:
        print(f"[EscalationEngine] {tracking_id}: not found in DB — skipping.")
        summary["errors"].append(f"{tracking_id}: not found in DB")
        return

    effective_age_hours = _get_effective_age(complaint_full)

    # ── SLA check ────────────────────────────────────────────────────────────
    sla = SLA_HOURS.get(int(severity), DEFAULT_SLA_HOURS)

    print(
        f"[EscalationEngine] {tracking_id}: "
        f"age={effective_age_hours:.1f}h, SLA={sla}h, severity={severity}, status={status}"
    )

    if effective_age_hours < sla:
        print(f"[EscalationEngine] {tracking_id}: within SLA — no action.")
        summary["skipped"] += 1
        return

    # ── SLA breached — escalate ──────────────────────────────────────────────
    print(f"[EscalationEngine] {tracking_id}: SLA BREACHED — escalating...")
    _escalate(complaint_full, status, summary)


def _escalate(complaint: dict, current_status: str, summary: dict):
    """
    Looks up the next authority level, updates DB, re-submits complaint.
    """
    tracking_id  = complaint["tracking_id"]
    current_level_num = STATUS_TO_LEVEL.get(current_status, 1)

    # ── Check if there's a next level ───────────────────────────────────────
    if current_level_num not in ESCALATION_LADDER:
        print(f"[EscalationEngine] {tracking_id}: no escalation path from level {current_level_num}.")
        summary["skipped"] += 1
        return

    next_level_num, next_status = ESCALATION_LADDER[current_level_num]
    next_level_key = f"level{next_level_num}"

    # ── Look up next authority from JSON ─────────────────────────────────────
    next_authority = _lookup_next_authority(complaint, next_level_key)
    if not next_authority:
        msg = (
            f"{tracking_id}: could not find level {next_level_num} authority "
            f"in authority_data.json — escalation aborted."
        )
        print(f"[EscalationEngine] WARNING: {msg}")
        summary["errors"].append(msg)
        return

    # ── Rebuild context for re-submission ────────────────────────────────────
    ctx = _build_context(complaint, next_authority, next_level_key, next_level_num)

    # ── Log escalation intent ─────────────────────────────────────────────────
    log_msg = (
        f"SLA breached (level {current_level_num}). "
        f"Escalating to {next_authority['authority']} (level {next_level_num})."
    )
    asyncio.run(insert_log(tracking_id, log_msg))
    print(f"[EscalationEngine] {tracking_id}: {log_msg}")

    # ── Update DB with new authority before re-submission ────────────────────
    asyncio.run(update_status(tracking_id, "submitting"))
    asyncio.run(save_complaint(ctx))

    # ── Re-submit via submission_agent ───────────────────────────────────────
    result = submit_complaint(asdict(ctx))

    new_status = next_status if result["success"] else "failed"

    # Persist result back to DB
    ctx.submission_status     = new_status
    ctx.submission_screenshot = result.get("submission_screenshot", "")
    if result.get("complaint_ref_id"):
        ctx.complaint_ref_id = result["complaint_ref_id"]

    asyncio.run(save_complaint(ctx))
    asyncio.run(update_status(tracking_id, new_status))

    outcome_msg = (
        f"Escalation to level {next_level_num} "
        f"({'succeeded' if result['success'] else 'failed'}). "
        f"New status: {new_status}."
    )
    asyncio.run(insert_log(tracking_id, outcome_msg))
    print(f"[EscalationEngine] {tracking_id}: {outcome_msg}")

    if result["success"]:
        summary["escalated"] += 1
    else:
        summary["errors"].append(
            f"{tracking_id}: re-submission failed at level {next_level_num} — {result['error']}"
        )


# ---------------------------------------------------------------------------
# Authority lookup
# ---------------------------------------------------------------------------

def _lookup_next_authority(complaint: dict, level_key: str) -> dict | None:
    """
    Finds the next-level authority dict from authority_data.json.
    Returns None if not found.
    """
    key = (
        (complaint.get("state") or "").strip().lower(),
        (complaint.get("district") or "").strip().lower(),
        (complaint.get("issue_type") or "").strip().lower(),
    )

    entry = _AUTHORITY_INDEX.get(key)
    if not entry:
        return None

    level_data = entry.get(level_key)
    if not level_data:
        return None

    return level_data


# ---------------------------------------------------------------------------
# Effective age calculation
# ---------------------------------------------------------------------------

def _get_effective_age(complaint: dict) -> float:
    """
    Returns the effective complaint age in hours.

    Priority:
        1. Ask dummy portal API — respects per-complaint clock offset
        2. Fall back to computing from DB submitted_at (no offset applied)
    """
    ref_id = complaint.get("complaint_ref_id", "")
    if ref_id:
        portal_age = _fetch_portal_age(ref_id)
        if portal_age is not None:
            return portal_age

    # Fallback: compute from DB timestamp
    return _age_from_db(complaint)


def _fetch_portal_age(complaint_ref_id: str) -> float | None:
    """
    Calls GET /api/complaint/<ref_id> on the dummy portal.
    Returns effective_age_hours float, or None if portal unreachable.
    """
    url = f"{DUMMY_PORTAL_URL}/api/complaint/{complaint_ref_id}"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode())
            age  = data.get("effective_age_hours")
            if age is not None:
                return float(age)
    except urllib.error.URLError:
        print(
            f"[EscalationEngine] Dummy portal unreachable at {DUMMY_PORTAL_URL} — "
            "falling back to DB timestamp for age calculation."
        )
    except Exception as e:
        print(f"[EscalationEngine] Portal age fetch error: {e}")
    return None


def _age_from_db(complaint: dict) -> float:
    """Computes complaint age in hours from DB submitted_at / created_at."""
    ts_str = complaint.get("created_at") or complaint.get("updated_at", "")
    if not ts_str:
        return 0.0
    try:
        submitted_at = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        delta = datetime.datetime.now() - submitted_at
        return delta.total_seconds() / 3600
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context(
    complaint: dict,
    next_authority: dict,
    level_key: str,
    level_num: int
) -> ComplaintContext:
    """
    Reconstructs a ComplaintContext from the DB complaint dict,
    updated with the next authority's details.
    """
    # Clamp severity to valid range before constructing
    severity = complaint.get("severity") or 1
    severity = max(0, min(int(severity), 5))

    ctx = ComplaintContext(
        tracking_id    = complaint["tracking_id"],
        user_id        = complaint.get("user_id", ""),
        video_path     = complaint.get("video_path", ""),

        issue_type     = complaint.get("issue_type", ""),
        state          = complaint.get("state", ""),
        district       = complaint.get("district", ""),
        location_label = complaint.get("location_label", ""),
        severity       = severity,
        transcript     = complaint.get("transcript", ""),

        complaint_text = complaint.get("complaint_text", ""),

        # Updated to next-level authority
        authority_name     = next_authority.get("authority", ""),
        authority_email    = next_authority.get("email", ""),
        authority_portal   = next_authority.get("portal", ""),
        authority_phone    = next_authority.get("phone", ""),
        authority_level    = level_key,
        authority_level_num= level_num,

        # Carry over existing submission artefacts
        submission_status     = "submitting",
        submission_screenshot = complaint.get("submission_screenshot", ""),
        complaint_ref_id      = complaint.get("complaint_ref_id", ""),
    )

    return ctx