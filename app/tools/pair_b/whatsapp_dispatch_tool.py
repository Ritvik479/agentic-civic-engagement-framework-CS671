"""
app/tools/pair_b/whatsapp_dispatch_tool.py
-------------------------------------------
Agent 5 — WhatsApp dispatch tool.

Sends (or mocks) a WhatsApp message to the mapped authority's WhatsApp
number, if one is available in the authority data.

Current mode: MOCKED — logs message payload to logs/whatsapp_mock_log.jsonl.

To switch to real WhatsApp delivery, two paths are available:
    A) Twilio Sandbox for WhatsApp (recommended for testing):
           WHATSAPP_PROVIDER = "twilio"
           TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
    B) Meta Cloud API (production, requires Meta app approval):
           WHATSAPP_PROVIDER = "meta"
           META_ACCESS_TOKEN, META_PHONE_NUMBER_ID

If none of these env vars are set, the tool mocks automatically.

Design:
- Sync function (tools are sync, orchestrator is async — team design choice)
- Returns plain dict matching team tool contract
- Secondary channel — a missing/invalid number is a soft failure (success=True,
  sent=False) so it never blocks portal submission or email dispatch
"""

import os
import json
import datetime
import traceback

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "").lower()  # "twilio" | "meta" | ""

# Twilio
TWILIO_ACCOUNT_SID    = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN     = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM  = os.getenv("TWILIO_WHATSAPP_FROM", "")  # e.g. "whatsapp:+14155238886"

# Meta Cloud API
META_ACCESS_TOKEN    = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")

MOCK_LOG_DIR  = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "logs"
)
MOCK_LOG_FILE = os.path.join(MOCK_LOG_DIR, "whatsapp_mock_log.jsonl")


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

def send_whatsapp_message(ctx: dict) -> dict:
    """
    Sends a WhatsApp message to the authority's WhatsApp number, if available.

    WhatsApp is a secondary channel — if the authority has no WhatsApp number
    or the number is invalid, the tool returns success=True with sent=False.
    This is intentional: a missing WhatsApp contact should never block the
    primary complaint submission flow.

    Args:
        ctx: Full complaint context dict (from dataclasses.asdict(ctx)).
             Key used: authority_phone (WhatsApp number), tracking_id,
             complaint_ref_id, issue_type, location_label, severity,
             authority_name, complaint_text

    Returns:
        {
            "success":  bool,  # False only on unexpected internal error
            "sent":     bool,  # True if message was actually dispatched/logged
            "mocked":   bool,  # True if written to log instead of real API
            "channel":  str,   # "twilio" | "meta" | "mock" | "skipped"
            "error":    str    # "" on success
        }
    """
    phone = _resolve_phone(ctx)

    if not phone:
        # Soft skip — not an error, just no WhatsApp contact available
        print("[WhatsAppDispatch] No WhatsApp number available — skipping.")
        return _skipped()

    message = _compose(ctx)

    if WHATSAPP_PROVIDER == "twilio" and _twilio_configured():
        return _send_twilio(phone, message)

    if WHATSAPP_PROVIDER == "meta" and _meta_configured():
        return _send_meta(phone, message, ctx)

    # Default: mock
    return _send_mock(phone, message, ctx)


# ---------------------------------------------------------------------------
# Message composition
# ---------------------------------------------------------------------------

def _compose(ctx: dict) -> str:
    """
    Composes a concise WhatsApp message. Kept short deliberately —
    WhatsApp is for alerting, not for the full complaint text (that goes
    via email and portal).
    """
    ref         = ctx.get("complaint_ref_id") or ctx.get("tracking_id", "N/A")
    issue       = ctx.get("issue_type", "Civic Issue")
    location    = (
        ctx.get("location_label")
        or f"{ctx.get('district', '')}, {ctx.get('state', '')}"
    )
    severity    = ctx.get("severity", "N/A")
    authority   = ctx.get("authority_name", "Your Office")
    date_str    = datetime.datetime.now().strftime("%d %b %Y, %I:%M %p")

    return (
        f"*NagrikVaani Complaint Alert*\n\n"
        f"A formal complaint has been filed with {authority}.\n\n"
        f"*Ref ID:* {ref}\n"
        f"*Issue:* {issue}\n"
        f"*Location:* {location}\n"
        f"*Severity:* {severity}/4\n"
        f"*Filed On:* {date_str}\n\n"
        f"A detailed complaint with supporting evidence has been sent to your "
        f"registered email. Please acknowledge within 48 hours.\n\n"
        f"_NagrikVaani — Automated Civic Complaint System_"
    )


# ---------------------------------------------------------------------------
# Phone resolution
# ---------------------------------------------------------------------------

def _resolve_phone(ctx: dict) -> str:
    """
    Returns a WhatsApp-ready phone number string, or "" if unavailable.

    ctx does not currently carry a phone field — authority_data.json has
    a 'phone' field per level. For now we read authority_phone from ctx
    if Trio C populates it in future, otherwise return "".

    To wire this up: add authority_phone to ComplaintContext and
    authority_lookup_tool.py return dict, then this works automatically.
    """
    raw = ctx.get("authority_phone", "").strip()
    if not raw:
        return ""

    # Normalise to E.164 — strip spaces, dashes, brackets
    digits = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if not digits:
        return ""

    # Ensure leading + for international format
    if not digits.startswith("+"):
        digits = "+91" + digits  # assume India if no country code

    # Basic sanity: E.164 is 8–15 digits after +
    digit_count = len(digits.replace("+", ""))
    if not (8 <= digit_count <= 15):
        print(f"[WhatsAppDispatch] Phone number looks invalid: {digits} — skipping.")
        return ""

    return digits


# ---------------------------------------------------------------------------
# Twilio sender
# ---------------------------------------------------------------------------

def _twilio_configured() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM])


def _send_twilio(to_phone: str, message: str) -> dict:
    """Sends via Twilio WhatsApp Sandbox."""
    try:
        from twilio.rest import Client  # optional dependency
    except ImportError:
        return {
            "success": False,
            "sent":    False,
            "mocked":  False,
            "channel": "twilio",
            "error":   "twilio package not installed. Run: pip install twilio"
        }

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        msg = client.messages.create(
            from_=TWILIO_WHATSAPP_FROM,
            to=f"whatsapp:{to_phone}",
            body=message
        )

        print(f"[WhatsAppDispatch] Sent via Twilio | SID: {msg.sid}")
        return {
            "success": True,
            "sent":    True,
            "mocked":  False,
            "channel": "twilio",
            "error":   ""
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "sent":    False,
            "mocked":  False,
            "channel": "twilio",
            "error":   f"Twilio send failed: {e}"
        }


# ---------------------------------------------------------------------------
# Meta Cloud API sender
# ---------------------------------------------------------------------------

def _meta_configured() -> bool:
    return all([META_ACCESS_TOKEN, META_PHONE_NUMBER_ID])


def _send_meta(to_phone: str, message: str, ctx: dict) -> dict:
    """Sends via Meta WhatsApp Cloud API."""
    try:
        import urllib.request

        url     = f"https://graph.facebook.com/v19.0/{META_PHONE_NUMBER_ID}/messages"
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "to":                to_phone,
            "type":              "text",
            "text":              {"body": message}
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {META_ACCESS_TOKEN}",
                "Content-Type":  "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = json.loads(resp.read().decode())

        msg_id = (
            resp_body.get("messages", [{}])[0].get("id", "unknown")
        )
        print(f"[WhatsAppDispatch] Sent via Meta API | Message ID: {msg_id}")

        return {
            "success": True,
            "sent":    True,
            "mocked":  False,
            "channel": "meta",
            "error":   ""
        }

    except Exception as e:
        traceback.print_exc()
        return {
            "success": False,
            "sent":    False,
            "mocked":  False,
            "channel": "meta",
            "error":   f"Meta API send failed: {e}"
        }


# ---------------------------------------------------------------------------
# Mock sender
# ---------------------------------------------------------------------------

def _send_mock(to_phone: str, message: str, ctx: dict) -> dict:
    """Logs the WhatsApp payload to logs/whatsapp_mock_log.jsonl."""
    os.makedirs(MOCK_LOG_DIR, exist_ok=True)

    timestamp = datetime.datetime.now().isoformat()

    payload = {
        "timestamp":     timestamp,
        "tracking_id":   ctx.get("tracking_id", "unknown"),
        "complaint_ref": ctx.get("complaint_ref_id", ""),
        "to":            to_phone,
        "message":       message,
        "authority":     ctx.get("authority_name", ""),
        "issue_type":    ctx.get("issue_type", ""),
        "severity":      ctx.get("severity", "")
    }

    try:
        with open(MOCK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

        print(
            f"[WhatsAppDispatch] MOCKED — logged to {MOCK_LOG_FILE}\n"
            f"  To: {to_phone}"
        )

        return {
            "success": True,
            "sent":    True,
            "mocked":  True,
            "channel": "mock",
            "error":   ""
        }

    except OSError as e:
        return {
            "success": False,
            "sent":    False,
            "mocked":  True,
            "channel": "mock",
            "error":   f"Failed to write mock WhatsApp log: {e}"
        }


# ---------------------------------------------------------------------------
# Skip return
# ---------------------------------------------------------------------------

def _skipped() -> dict:
    """Returned when no WhatsApp number is available. Not an error."""
    return {
        "success": True,
        "sent":    False,
        "mocked":  False,
        "channel": "skipped",
        "error":   ""
    }