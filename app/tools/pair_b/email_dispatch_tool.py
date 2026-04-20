"""
app/tools/pair_b/email_dispatch_tool.py
----------------------------------------
Agent 5 — Email dispatch tool.

Composes and sends a formal complaint email to the mapped authority,
with the complaint text drafted by Trio C (Agent 4).

Current mode: MOCKED — logs email payload to file, does not send over SMTP.
To switch to real SMTP (e.g. Mailtrap), replace _send_mock() with
_send_smtp() and set the four env vars listed below.

Env vars for real SMTP (optional, for when Mailtrap is set up):
    SMTP_HOST      e.g. "smtp.mailtrap.io"
    SMTP_PORT      e.g. "587"
    SMTP_USER      from Mailtrap inbox credentials
    SMTP_PASS      from Mailtrap inbox credentials
    EMAIL_FROM     sender address, e.g. "complaints@nagrikvaani.in"

Design:
- Sync function (tools are sync, orchestrator is async — team design choice)
- Returns plain dict matching team tool contract
- Mock mode writes to logs/email_mock_log.jsonl (one JSON object per line)
"""

import os
import json
import datetime
import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.utils import make_msgid
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SMTP_HOST  = os.getenv("SMTP_HOST", "")
SMTP_PORT  = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER  = os.getenv("SMTP_USER", "")
SMTP_PASS  = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "complaints@nagrikvaani.in")

# If all four SMTP vars are set, use real SMTP — otherwise mock
_SMTP_CONFIGURED = all([SMTP_HOST, SMTP_USER, SMTP_PASS, EMAIL_FROM])

MOCK_LOG_DIR  = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "logs"
)
MOCK_LOG_FILE = os.path.join(MOCK_LOG_DIR, "email_mock_log.jsonl")


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

def send_complaint_email(ctx: dict) -> dict:
    """
    Composes and dispatches a formal complaint email to the mapped authority.

    Args:
        ctx: Full complaint context dict (from dataclasses.asdict(ctx)).
             Required keys:
                tracking_id, authority_email, authority_name,
                issue_type, state, district, location_label,
                severity, complaint_text, complaint_ref_id

    Returns:
        {
            "success":    bool,
            "mocked":     bool,   # True if sent to mock log, not real SMTP
            "message_id": str,    # SMTP message ID, or mock log filename
            "error":      str     # "" on success
        }
    """
    authority_email = ctx.get("authority_email", "").strip()

    # ── Guard: no recipient ──
    if not authority_email:
        return {
            "success":    False,
            "mocked":     not _SMTP_CONFIGURED,
            "message_id": "",
            "error":      "No authority email found in context — cannot dispatch."
        }

    subject, body = _compose(ctx)

    if _SMTP_CONFIGURED:
        return _send_smtp(authority_email, subject, body, ctx)
    else:
        return _send_mock(authority_email, subject, body, ctx)


# ---------------------------------------------------------------------------
# Email composition
# ---------------------------------------------------------------------------

def _compose(ctx: dict) -> tuple[str, str]:
    """Returns (subject, plain-text body) for the complaint email."""

    tracking_id    = ctx.get("tracking_id", "N/A")
    complaint_ref  = ctx.get("complaint_ref_id", "N/A")
    authority_name = ctx.get("authority_name", "Concerned Authority")
    issue_type     = ctx.get("issue_type", "Civic Issue")
    location       = (
        ctx.get("location_label")
        or f"{ctx.get('district', '')}, {ctx.get('state', '')}"
    )
    severity       = ctx.get("severity", "N/A")
    complaint_text = ctx.get("complaint_text", "").strip()
    date_str       = datetime.datetime.now().strftime("%d %B %Y")

    subject = (
        f"Formal Complaint: {issue_type} at {location} "
        f"[Ref: {complaint_ref} | Tracking: {tracking_id}]"
    )

    # new fields from updated context
    citizen_name  = ctx.get("name", "").strip() or "Citizen Complainant"
    citizen_email = ctx.get("email", "").strip()
    citizen_phone = ctx.get("phone", "").strip()

    contact_line = citizen_email
    if citizen_phone:
        contact_line += f" | {citizen_phone}"

    body = f"""
    To,
    The {authority_name},

    Subject: Formal Complaint Regarding {issue_type} at {location}

    Date: {date_str}
    Complaint Reference ID: {complaint_ref}
    System Tracking ID: {tracking_id}
    Severity Level: {severity} / 5

    Dear Sir/Madam,

    {complaint_text}

    This complaint has been filed through the NagrikVaani Automated Civic
    Complaint System on behalf of a citizen who has documented this violation.
    Supporting evidence (video/images) was captured at the location mentioned above.

    We request that the concerned authority:
    1. Acknowledge receipt of this complaint within 48 hours.
    2. Initiate an on-ground inspection at the earliest.
    3. Provide a resolution timeline and action taken report.

    Failure to respond within the prescribed SLA may result in automatic
    escalation to higher authorities.

    Yours faithfully,
    {citizen_name}
    Filed via NagrikVaani — Automated Civic Grievance Platform
    Contact: {contact_line}
    ---
    This is a system-generated email. For queries, cite Ref: {complaint_ref}.
    """.strip()

    return subject, body


# ---------------------------------------------------------------------------
# Send via real SMTP
# ---------------------------------------------------------------------------

def _send_smtp(
    to_email: str,
    subject: str,
    body: str,
    ctx: dict
) -> dict:
    """Sends email over SMTP (e.g. Mailtrap). Used when SMTP env vars are set."""

    msg = MIMEMultipart("alternative")
    msg["From"]       = EMAIL_FROM
    msg["To"]         = to_email
    msg["Subject"]    = subject
    msg["Message-ID"] = make_msgid(domain="nagrikvaani.in")

    # CC: could be extended to include state/central oversight addresses
    cc_addresses = _build_cc(ctx)
    if cc_addresses:
        msg["Cc"] = ", ".join(cc_addresses)

    msg.attach(MIMEText(body, "plain"))

    recipients = [to_email] + cc_addresses

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, recipients, msg.as_string())

        message_id = msg["Message-ID"]
        print(f"[EmailDispatch] Email sent to {to_email} | ID: {message_id}")

        return {
            "success":    True,
            "mocked":     False,
            "message_id": message_id,
            "error":      ""
        }

    except smtplib.SMTPException as e:
        print(f"[EmailDispatch] SMTP error: {e}")
        return {
            "success":    False,
            "mocked":     False,
            "message_id": "",
            "error":      f"SMTP error: {e}"
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "success":    False,
            "mocked":     False,
            "message_id": "",
            "error":      f"Unexpected error sending email: {e}"
        }


# ---------------------------------------------------------------------------
# Mock send — write to log file
# ---------------------------------------------------------------------------

def _send_mock(
    to_email: str,
    subject: str,
    body: str,
    ctx: dict
) -> dict:
    """
    Logs the email payload to logs/email_mock_log.jsonl instead of sending.
    Each line is a self-contained JSON object for easy inspection.
    """
    os.makedirs(MOCK_LOG_DIR, exist_ok=True)

    timestamp  = datetime.datetime.now().isoformat()
    tracking_id = ctx.get("tracking_id", "unknown")

    payload = {
        "timestamp":      timestamp,
        "tracking_id":    tracking_id,
        "complaint_ref":  ctx.get("complaint_ref_id", ""),
        "from":           EMAIL_FROM,
        "to":             to_email,
        "cc":             _build_cc(ctx),
        "subject":        subject,
        "body":           body,
        "authority_name": ctx.get("authority_name", ""),
        "issue_type":     ctx.get("issue_type", ""),
        "severity":       ctx.get("severity", ""),
        "location":       (
            ctx.get("location_label")
            or f"{ctx.get('district', '')}, {ctx.get('state', '')}"
        )
    }

    try:
        with open(MOCK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        mock_id = f"mock-{tracking_id}-{timestamp}"
        print(
            f"[EmailDispatch] MOCKED — logged to {MOCK_LOG_FILE}\n"
            f"  To:      {to_email}\n"
            f"  Subject: {subject[:80]}..."
        )

        return {
            "success":    True,
            "mocked":     True,
            "message_id": mock_id,
            "error":      ""
        }

    except OSError as e:
        return {
            "success":    False,
            "mocked":     True,
            "message_id": "",
            "error":      f"Failed to write mock email log: {e}"
        }


# ---------------------------------------------------------------------------
# CC chain builder
# ---------------------------------------------------------------------------

def _build_cc(ctx: dict) -> list[str]:
    """
    Builds a CC list for oversight.
    Currently a stub — extend this when escalation levels are integrated.
    Returns a list of email strings (may be empty).

    Future: pull level2/level3 emails from authority_data.json based on
    ctx["authority_level_num"] to build a proper oversight CC chain.
    """
    cc = []

    # Example: always CC CPCB for severity 4 environmental issues
    if ctx.get("severity") == 4 and "pollution" in ctx.get("issue_type", "").lower():
        cc.append("head_office@cpcb.nic.in")

    return cc