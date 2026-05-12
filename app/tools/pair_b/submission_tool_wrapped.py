"""
app/tools/pair_b/submission_tool_wrapped.py

smolagents @tool wrapper for the submission stage (pair_b).

Responsibility
──────────────
Take a validated FinalComplaint, translate it into the ctx dict that
submit_complaint() in submission_agent_tool.py expects, dispatch the
complaint across all configured channels (portal → email → WhatsApp),
and return an updated FinalComplaint reflecting the outcome.

Pipeline position
─────────────────
    FinalComplaint (JSON str) ──► submission_tool ──► FinalComplaint (JSON str)
                                                       status = SUBMITTED | error

Internal call chain
───────────────────
    1. Deserialise FinalComplaint via model_validate_json().
    2. Build ctx dict from model_dump() + explicit field remapping.
    3. Call submit_complaint(ctx) from submission_agent_tool.py.
    4. Inspect result["submission_status"] (NOT result["status"]) —
       the key in submit_complaint's return dict is "submission_status".
    5a. If "submitted"  → return FinalComplaint with status=SUBMITTED and
        complaint_id populated from result["complaint_ref_id"].
    5b. If "email_only" → submission reached the authority via email even
        though the portal failed.  Treated as a successful submission variant;
        returns SUBMITTED with a note in submission_response.
    5c. Otherwise       → return {"error": ...}.

Field remapping (FinalComplaint → ctx)
───────────────────────────────────────
    FinalComplaint field          ctx key            Notes
    ─────────────────────────     ──────────────     ──────────────────────────
    run_id  (UUID)             → tracking_id  (str)  str(uuid) for portals
    submission_endpoint        → authority_email     email or API URL
    issue_description          → complaint_text      LLM-authored narrative
    issue_category.value       → issue_type          string enum value
    severity.value             → severity            string; agent interprets
    submission_endpoint        → authority_portal    ⚠ FinalComplaint has no
                                                       separate portal_url field.
                                                       submit_complaint aborts if
                                                       authority_portal is falsy,
                                                       so we reuse submission_
                                                       endpoint as the best
                                                       available fallback.
                                                       When AuthorityContact
                                                       gains a portal_url field
                                                       that is propagated into
                                                       FinalComplaint, update
                                                       this mapping.

Constraints
───────────
- DO NOT modify submission_agent_tool.py.
- DO NOT import app.context anywhere in this file.
- On any unhandled exception return json.dumps({"error": str(e)}).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from smolagents import tool

from app.schemas.issue_schema import ComplaintStatus, FinalComplaint
from app.tools.pair_b.submission_agent_tool import submit_complaint

logger = logging.getLogger(__name__)


@tool
def submission_tool(final_complaint_json: str) -> str:
    """
    Submit a validated FinalComplaint to the appropriate government authority
    via all configured channels (portal, email, WhatsApp) and return the
    updated complaint with submission tracking details.

    This is the terminal execution-layer step in the pipeline.  It wraps
    submit_complaint() from submission_agent_tool.py, which orchestrates:
      1. Playwright-based portal form submission (primary channel).
      2. Formal email dispatch (fallback if portal fails).
      3. WhatsApp alert (best-effort secondary; never blocks the result).

    The tool maps the schema-driven FinalComplaint into the flat ctx dict
    format that submit_complaint() requires, then maps the result back into
    an updated FinalComplaint.

    Call this tool ONLY after complaint_assembly_tool has returned a
    FinalComplaint with status=VALIDATED.  Passing a DRAFT or FAILED complaint
    will likely trigger the abort guard inside submit_complaint (authority_portal
    missing or authority_name unknown).

    Args:
        final_complaint_json: JSON string of a FinalComplaint object with
            status=VALIDATED.  Must be produced by FinalComplaint.model_dump_json().
            Required fields for a successful submission:
              - authority_name   (must not be "Unknown Authority")
              - submission_endpoint  (used as both authority_email and
                                      authority_portal fallback)
              - issue_description, issue_category, severity, issue_location
              - run_id, authority_code, source_url

    Returns:
        On success ("submitted" or "email_only"):
            JSON string of the updated FinalComplaint with:
              - status = "submitted"
              - complaint_id populated from the portal reference number
                (empty string if only email succeeded)
              - submitted_at set to the current UTC timestamp
              - submission_response containing the full result dict from
                submit_complaint() for auditability
            Parse with FinalComplaint.model_validate_json().

        On failure:
            JSON string of the form {"error": "<message>"}.
            The CodeAgent should treat this as a terminal pipeline failure
            and flag the run for human review or escalation.

    Example (CodeAgent generated code):
        result = submission_tool(final_complaint_json=complaint_json)
        if "error" not in result:
            submitted = FinalComplaint.model_validate_json(result)
            print(submitted.complaint_id)
        else:
            error_data = json.loads(result)
            print("Submission failed:", error_data["error"])
    """
    try:
        # ------------------------------------------------------------------
        # Step 1 — Deserialise input
        # ------------------------------------------------------------------
        complaint = FinalComplaint.model_validate_json(final_complaint_json)

        logger.info(
            "[submission_tool] Starting submission  run_id=%s  authority=%s  status=%s",
            complaint.run_id,
            complaint.authority_code,
            complaint.status,
        )

        # ------------------------------------------------------------------
        # Step 2 — Build ctx dict
        # Start with a full model_dump() so all FinalComplaint fields are
        # present (submission_agent sub-tools may read arbitrary fields),
        # then apply the explicit remappings on top.
        #
        # model_dump() serialises:
        #   - UUID   → uuid.UUID  (need str for portal/email tools)
        #   - Enum   → enum instance (need .value for portal/email tools)
        #   - HttpUrl→ Pydantic Url object (need str)
        # We use mode="json" to get all primitives, then remap.
        # ------------------------------------------------------------------
        base: dict = json.loads(complaint.model_dump_json())  # all primitives

        ctx: dict = {
            **base,  # carry every FinalComplaint field as-is first

            # ── Explicit remappings ─────────────────────────────────────
            # run_id (UUID str in base) → tracking_id
            "tracking_id":      str(complaint.run_id),

            # submission_endpoint → authority_email
            "authority_email":  complaint.submission_endpoint or "",

            # issue_description → complaint_text
            "complaint_text":   complaint.issue_description,

            # issue_category.value → issue_type
            "issue_type":       complaint.issue_category.value,

            # severity.value → severity  (submission_agent interprets the string)
            "severity":         complaint.severity.value,

            # ── authority_portal fallback ───────────────────────────────
            # submit_complaint has a hard abort guard:
            #   if not ctx.get("authority_portal"): → return failed
            # FinalComplaint has no dedicated portal_url field (it was not
            # propagated from AuthorityContact).  We reuse submission_endpoint
            # as the best available proxy.
            # TODO: When FinalComplaint gains an authority_portal field
            #       (e.g. from AuthorityContact.portal_url), update this line.
            "authority_portal": complaint.submission_endpoint or "",
        }

        logger.debug(
            "[submission_tool] ctx prepared  tracking_id=%s  authority_email=%s  "
            "authority_portal=%s  issue_type=%s  severity=%s",
            ctx["tracking_id"],
            ctx["authority_email"],
            ctx["authority_portal"],
            ctx["issue_type"],
            ctx["severity"],
        )

        # ------------------------------------------------------------------
        # Step 3 — Call submit_complaint
        # Returns a dict with key "submission_status" (NOT "status").
        # Possible values: "submitted" | "email_only" | "failed"
        # ------------------------------------------------------------------
        result: dict = submit_complaint(ctx)

        submission_status: str = result.get("submission_status", "failed")

        logger.info(
            "[submission_tool] submit_complaint returned  run_id=%s  "
            "submission_status=%s  success=%s",
            complaint.run_id,
            submission_status,
            result.get("success"),
        )

        # ------------------------------------------------------------------
        # Step 4a — Portal success: status == "submitted"
        # ------------------------------------------------------------------
        if submission_status == "submitted":
            updated = complaint.model_copy(
                update={
                    "status":              ComplaintStatus.SUBMITTED,
                    "complaint_id":        result.get("complaint_ref_id", ""),
                    "submitted_at":        datetime.now(tz=timezone.utc),
                    # follow_up_due is auto-computed by FinalComplaint's
                    # model_validator when submitted_at is set.
                    "submission_response": result,
                }
            )

            logger.info(
                "[submission_tool] Complaint submitted via portal  run_id=%s  "
                "complaint_id=%s",
                updated.run_id,
                updated.complaint_id,
            )
            return updated.model_dump_json()

        # ------------------------------------------------------------------
        # Step 4b — Email fallback: status == "email_only"
        # Portal failed but email reached the authority.  Treated as a
        # successful submission variant — the complaint is in the authority's
        # inbox even without a portal reference number.
        # ------------------------------------------------------------------
        if submission_status == "email_only":
            updated = complaint.model_copy(
                update={
                    "status":              ComplaintStatus.SUBMITTED,
                    "complaint_id":        "",   # no portal ref; email has no ref id
                    "submitted_at":        datetime.now(tz=timezone.utc),
                    "submission_response": result,
                    "validation_errors":   [
                        "Portal submission failed; complaint delivered via email only. "
                        "No portal reference number available."
                    ],
                }
            )

            logger.warning(
                "[submission_tool] Complaint submitted via email only (portal failed)  "
                "run_id=%s",
                updated.run_id,
            )
            return updated.model_dump_json()

        # ------------------------------------------------------------------
        # Step 4c — Both channels failed
        # ------------------------------------------------------------------
        error_msg = result.get("error") or "submission failed"

        logger.error(
            "[submission_tool] All channels failed  run_id=%s  error=%s",
            complaint.run_id,
            error_msg,
        )
        return json.dumps({"error": error_msg})

    except Exception as e:
        logger.exception(
            "[submission_tool] Unhandled exception  error=%s", e
        )
        return json.dumps({"error": str(e)})
