"""
app/tools/pair_b/portal_navigator_tool.py
------------------------------------------
Agent 5 — Playwright-based form automation tool.

Navigates the dummy portal (or any target portal URL), fills the complaint
form using context data supplied by upstream agents, submits it, and extracts
the complaint reference ID from the confirmation page.

Design decisions:
- Sync function (orchestrator is async, tools are sync — team design choice)
- Graceful fallback if portal is unreachable
- Screenshots saved to screenshots/ directory on success and on error
- Returns plain dict matching team tool contract
"""

import os
import time
import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORTAL_BASE_URL = os.getenv("DUMMY_PORTAL_URL", "http://localhost:5050")
SCREENSHOT_DIR  = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "screenshots"
)
NAVIGATION_TIMEOUT_MS = 8_000   # how long to wait when loading a page
ACTION_TIMEOUT_MS     = 5_000   # how long to wait for a specific element
FORM_URL              = f"{PORTAL_BASE_URL}/complaint/new"
HOME_URL              = f"{PORTAL_BASE_URL}/"


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

def submit_to_portal(ctx: dict) -> dict:
    """
    Navigates the complaint portal, fills the form, submits, and returns
    the assigned complaint reference ID.

    Args:
        ctx: Full complaint context dict (from dataclasses.asdict(ctx)).
             Required keys used:
                tracking_id, full_name (or user_id), email,
                issue_type, state, district, location_label,
                severity, description (complaint_text), authority_name

    Returns:
        {
            "success":           bool,
            "complaint_ref_id":  str,   # e.g. "COMP-20250417-AB1C2D"
            "submission_screenshot":        str,   # file path, or "" on failure
            "error":             str    # "" on success
        }
    """
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    # ── Pre-flight: check if portal is reachable before launching browser ──
    if not _portal_reachable():
        return {
            "success":          False,
            "complaint_ref_id": "",
            "submission_screenshot":       "",
            "error":            (
                f"Portal unreachable at {PORTAL_BASE_URL}. "
                "Ensure dummy_portal/app.py is running."
            )
        }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page    = browser.new_page()

        try:
            result = _run_form_flow(page, ctx)
        except Exception as e:
            # Unexpected error — capture screenshot before bailing
            error_shot = _save_screenshot(page, ctx.get("tracking_id", "unknown"), tag="error")
            result = {
                "success":          False,
                "complaint_ref_id": "",
                "submission_screenshot":       error_shot,
                "error":            f"Unexpected error during portal navigation: {e}"
            }
        finally:
            browser.close()

    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _portal_reachable() -> bool:
    """
    Lightweight TCP check — does not launch a browser.
    Returns True if the portal's host:port is accepting connections.
    """
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(PORTAL_BASE_URL)
    host   = parsed.hostname or "localhost"
    port   = parsed.port or 5050

    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _run_form_flow(page, ctx: dict) -> dict:
    """
    Full navigation flow:
      Home → click 'File a Complaint' → fill form → submit → extract ref ID
    """
    tracking_id = ctx.get("tracking_id", "unknown")

    # ── Step 1: Land on home page, navigate to form via button ──
    # This tests the full navigation path Playwright would take on a real portal
    try:
        page.goto(HOME_URL, timeout=NAVIGATION_TIMEOUT_MS)
        page.wait_for_load_state("domcontentloaded")
    except PlaywrightTimeoutError:
        return _fail("Timed out loading portal home page.", page, tracking_id)

    try:
        page.get_by_role("link", name="File a Complaint").click()
        page.wait_for_url(f"{PORTAL_BASE_URL}/complaint/new", timeout=NAVIGATION_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        return _fail("Could not navigate from home to complaint form.", page, tracking_id)

    # ── Step 2: Fill hidden / agent-supplied fields via JS injection ──
    # These fields are not visible to the user — agents populate them directly.
    # Using evaluate() because fill() requires a visible element.
    _inject_hidden_field(page, "tracking_id",   str(ctx.get("tracking_id", "")))
    _inject_hidden_field(page, "authority_name", str(ctx.get("authority_name", "")))
    _inject_hidden_field(page, "severity",       str(ctx.get("severity", "2")))

    # ── Step 3: Fill visible form fields ──
    try:
        # Complainant details
        # Use user_id as fallback name if no dedicated name field in ctx
        full_name = ctx.get("name") or ctx.get("user_id") or "Citizen Complainant"
        _fill(page, "#full_name", full_name)
        _fill(page, "#email", ctx.get("email") or "complaint@nagrikvaani.test")
        _fill(page, "#phone", ctx.get("phone", ""))

        # Location — state uses a <select>, district and label use text inputs
        _select_by_label(page, "#state",          ctx.get("state", ""))
        _fill(page, "#district",                  ctx.get("district", ""))
        _fill(page, "#location_label",            ctx.get("location_label", ""))

        # Issue type — also a <select>
        issue_type = ctx.get("issue_type") or "Other"
        _select_by_label(page, "#issue_type", issue_type)

        # Description — use complaint_text drafted by Trio C
        description = ctx.get("complaint_text") or ctx.get("transcript") or "Civic issue reported via NagrikVaani automated system."
        _fill(page, "#description",               description[:2000])  # portal maxlength

    except PlaywrightTimeoutError as e:
        return _fail(f"Form fill timed out: {e}", page, tracking_id)

    # ── Step 4: Submit ──
    # ── Step 4: Submit ──
    try:
        _save_screenshot(page, tracking_id, tag="before_submit")
        print(f"[PortalNavigator] Current URL before submit: {page.url}")
        print(f"[PortalNavigator] Button visible: {page.locator('button.btn-submit').is_visible()}")
        page.locator("button.btn-submit").click()
        print(f"[PortalNavigator] Click fired, waiting for redirect...")
        page.wait_for_url(
            f"{PORTAL_BASE_URL}/complaint/confirm/*",
            timeout=NAVIGATION_TIMEOUT_MS
        )
    except PlaywrightTimeoutError:
        _save_screenshot(page, tracking_id, tag="after_timeout")
        print(f"[PortalNavigator] URL after timeout: {page.url}")
        return _fail("Timed out waiting for confirmation page after submit.", page, tracking_id)

    # ── Step 5: Extract complaint reference ID ──
    # confirmation.html renders the ID in <div id="complaint-ref-id">
    try:
        ref_element = page.locator("#complaint-ref-id")
        ref_element.wait_for(timeout=ACTION_TIMEOUT_MS)
        complaint_ref_id = ref_element.inner_text().strip()
    except PlaywrightTimeoutError:
        return _fail("Confirmation page loaded but ref ID element not found.", page, tracking_id)

    if not complaint_ref_id:
        return _fail("Complaint ref ID element was empty.", page, tracking_id)

    # ── Step 6: Screenshot of confirmation page ──
    screenshot_path = _save_screenshot(page, tracking_id, tag="confirmation")

    return {
        "success":          True,
        "complaint_ref_id": complaint_ref_id,
        "submission_screenshot":       screenshot_path,
        "error":            ""
    }


def _fill(page, selector: str, value: str):
    """Fill a visible text input or textarea, waiting for it to appear first."""
    locator = page.locator(selector)
    locator.wait_for(timeout=ACTION_TIMEOUT_MS)
    locator.fill(value)


def _select_by_label(page, selector: str, label: str):
    """
    Select a <select> option by its visible text label.
    Falls back silently if no matching option exists — avoids crashing on
    state/issue values not present in the dropdown.
    """
    locator = page.locator(selector)
    locator.wait_for(timeout=ACTION_TIMEOUT_MS)

    # Collect all available option labels for fallback matching
    option_labels: list[str] = locator.locator("option").all_inner_texts()

    # Try exact match first
    if label in option_labels:
        locator.select_option(label=label)
        return

    # Try case-insensitive match
    for opt in option_labels:
        if opt.strip().lower() == label.strip().lower():
            locator.select_option(label=opt)
            return

    # No match — leave at default, log warning (don't crash)
    print(
        f"[PortalNavigator] WARNING: '{label}' not found in {selector} options. "
        f"Available: {option_labels}. Leaving at default."
    )


# FIX
def _inject_hidden_field(page, field_id: str, value: str):
    page.evaluate(
        "([id, val]) => { const el = document.getElementById(id); if (el) el.value = val; }",
        [field_id, value]
    )


def _save_screenshot(page, tracking_id: str, tag: str = "screenshot") -> str:
    """Saves a screenshot and returns the file path."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{tracking_id}_{tag}_{timestamp}.png"
    filepath  = os.path.join(SCREENSHOT_DIR, filename)

    try:
        page.screenshot(path=filepath, full_page=True)
        print(f"[PortalNavigator] Screenshot saved: {filepath}")
    except Exception as e:
        print(f"[PortalNavigator] Screenshot failed: {e}")
        filepath = ""

    return filepath


def _fail(reason: str, page, tracking_id: str) -> dict:
    """Unified failure return — always captures an error screenshot."""
    print(f"[PortalNavigator] FAILED: {reason}")
    screenshot = _save_screenshot(page, tracking_id, tag="error")
    return {
        "success":          False,
        "complaint_ref_id": "",
        "submission_screenshot":       screenshot,
        "error":            reason
    }