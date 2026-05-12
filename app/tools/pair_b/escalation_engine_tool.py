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
from uuid import UUID

from app.schemas.issue_schema import (
    FinalComplaint,
    IssueCategory,
    SeverityLevel,
    ComplaintStatus,
)
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
    0: 72,   # informational — treat same as low severity
    1: 72,
    2: 48,
    3: 24,
    4: 12,
    5: 6,    # critical — escalate fast
}
DEFAULT_SLA_HOURS = 48  # kept as safety net, should never fire now

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
    "authority_mapped",   # ADD — waiting for orchestrator to resume after location confirmation
}

# Map current status → current level number (for authority lookup)
STATUS_TO_LEVEL: dict[str, int] = {
    "submitted":    1,
    "email_only":   2,   # portal already failed at l1 — skip straight to l2
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
# Severity int → SeverityLevel enum
# ---------------------------------------------------------------------------

_INT_TO_SEVERITY: dict[int, SeverityLevel] = {
    0: SeverityLevel.LOW,
    1: SeverityLevel.LOW,
    2: SeverityLevel.MEDIUM,
    3: SeverityLevel.HIGH,
    4: SeverityLevel.CRITICAL,
    5: SeverityLevel.CRITICAL,
}

# ---------------------------------------------------------------------------
# Authority data — loaded once at module import
# ---------------------------------------------------------------------------

def _load_authority_data() -> list[dict]:
    try:
        with open(AUTHORITY_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)["data"]
    except FileNotFoundError:
        raise RuntimeError(
            f"[EscalationEngine] FATAL: authority_data.json not found at "
            f"{AUTHORITY_DATA_PATH}. Cannot start escalation engine."
        )
    except (KeyError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"[EscalationEngine] FATAL: authority_data.json is malformed: {e}"
        )

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
    """Sync entry point for APScheduler."""
    return asyncio.run(_run_escalation_check_async())

async def _run_escalation_check_async() -> dict:
    summary = {"checked": 0, "escalated": 0, "skipped": 0, "errors": []}
    all_complaints = await fetch_slim_complaints()
    escalatable = [c for c in all_complaints if c.get("submission_status") in ESCALATABLE_STATUSES]

    for slim in escalatable:
        tracking_id = slim["tracking_id"]
        try:
            await _process_complaint(tracking_id, slim, summary)
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

async def _process_complaint(tracking_id: str, slim: dict, summary: dict):
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
    complaint_full = await fetch_complaint(tracking_id)
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
    await _escalate(complaint_full, status, summary)


async def _escalate(complaint: dict, current_status: str, summary: dict):
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
    await insert_log(tracking_id, log_msg)
    print(f"[EscalationEngine] {tracking_id}: {log_msg}")

    # ── Update DB with new authority before re-submission ────────────────────
    await save_complaint(ctx.model_dump())      # persist new authority first
    await update_status(tracking_id, "submitting")  # then flip status

    # ── Re-submit via submission_agent ───────────────────────────────────────
    result = submit_complaint(ctx.model_dump())

    new_status = next_status if result["success"] else "failed"

    # Persist result back to DB
    ctx = ctx.model_copy(update={
        "status": ComplaintStatus.SUBMITTED if result["success"] else ComplaintStatus.FAILED,
        "submission_endpoint": result.get("submission_screenshot", ctx.submission_endpoint),
    })
    if result.get("complaint_ref_id"):
        ctx = ctx.model_copy(update={"complaint_id": result["complaint_ref_id"]})

    await save_complaint(ctx.model_dump())
    await update_status(tracking_id, new_status)

    outcome_msg = (
        f"Escalation to level {next_level_num} "
        f"({'succeeded' if result['success'] else 'failed'}). "
        f"New status: {new_status}."
    )
    await insert_log(tracking_id, outcome_msg)
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
    ts_str = complaint.get("created_at") or complaint.get("updated_at", "")
    if not ts_str:
        return 0.0
    try:
        submitted_at = datetime.datetime.fromisoformat(ts_str)
        # Strip tzinfo if present to allow naive subtraction
        if submitted_at.tzinfo is not None:
            submitted_at = submitted_at.replace(tzinfo=None)
        delta = datetime.datetime.now() - submitted_at
        return delta.total_seconds() / 3600
    except (ValueError, TypeError):
        print(f"[EscalationEngine] WARNING: Could not parse timestamp '{ts_str}' — defaulting age to 0.0h")
        return 0.0


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------

def _build_context(
    complaint: dict,
    next_authority: dict,
    level_key: str,
    level_num: int,
) -> FinalComplaint:
    """
    Constructs a FinalComplaint from the DB complaint dict,
    updated with the next authority's details.

    Field mapping from old ComplaintContext:
        tracking_id    → run_id          (str cast to UUID)
        authority_name → authority_name
        authority_email→ submission_endpoint
        complaint_text → issue_description
        issue_type     → issue_category  (IssueCategory enum)
        severity (int) → severity        (SeverityLevel enum)
        authority_level→ status          (ComplaintStatus enum)
    """
    # Clamp severity to valid range
    severity_int = complaint.get("severity") or 1
    severity_int = max(0, min(int(severity_int), 5))
    severity_enum = _INT_TO_SEVERITY.get(severity_int, SeverityLevel.MEDIUM)

    # Map issue_type string → IssueCategory enum, falling back to UNKNOWN
    raw_issue_type = (complaint.get("issue_type") or "unknown").strip().lower()
    try:
        issue_category = IssueCategory(raw_issue_type)
    except ValueError:
        issue_category = IssueCategory.UNKNOWN

    # tracking_id is a plain string in the DB; run_id is a UUID in the schema
    tracking_id_str = complaint.get("tracking_id", "")
    try:
        run_id = UUID(tracking_id_str)
    except (ValueError, AttributeError):
        # If the string isn't a valid UUID (legacy data), generate a deterministic
        # one by zero-padding — keeps traceability without crashing.
        import uuid
        run_id = uuid.uuid5(uuid.NAMESPACE_DNS, tracking_id_str)

    # authority_level string ("level1", "level2", …) → ComplaintStatus
    # During escalation the complaint is being re-submitted, so SUBMITTED is
    # the appropriate terminal status; DRAFT signals it hasn't been sent yet.
    authority_level = complaint.get("authority_level", "")
    if authority_level in ("level2", "level3", "level4"):
        complaint_status = ComplaintStatus.SUBMITTED
    else:
        complaint_status = ComplaintStatus.DRAFT

    return FinalComplaint(
        run_id=run_id,
        status=complaint_status,

        # Source information — carry over from DB record
        source_url=complaint.get("video_path", ""),
        platform=complaint.get("platform", ""),
        reporter_handle=complaint.get("user_id") or None,
        posted_at=datetime.datetime.now(datetime.timezone.utc),  # best available

        # Issue fields
        issue_category=issue_category,
        severity=severity_enum,
        issue_location=(
            complaint.get("location_label")
            or complaint.get("district")
            or "Location not determined"
        ),
        issue_description=complaint.get("complaint_text", ""),

        # Evidence
        evidence_urls=[complaint.get("video_path", "")] if complaint.get("video_path") else [],

        # Next-level authority fields
        authority_name=next_authority.get("authority", ""),
        authority_code=next_authority.get("code", f"L{level_num}-UNKNOWN"),
        submission_endpoint=next_authority.get("email", "") or next_authority.get("portal", ""),

        # Submission tracking — carry over existing ref if present
        complaint_id=complaint.get("complaint_ref_id") or None,
    )