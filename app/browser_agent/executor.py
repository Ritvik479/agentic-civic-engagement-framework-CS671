"""
executor.py  —  translates the LLM's action dict into Playwright calls.

Supported action types:
    fill     — type into a text input
    click    — click a button or link
    check    — tick a checkbox
    select   — choose an option in a select2 / combobox dropdown
    captcha  — pause and ask the user to type the captcha manually
    wait     — short pause (page settling / retry)
    done     — terminal; caller should break the loop
    navigate — go to an explicit URL
"""

from playwright.sync_api import Page


# =====================================================
# PUBLIC ENTRY POINT
# =====================================================

def execute_action(page: Page, action: dict, memory: dict) -> str:
    """
    Execute *action* on *page*, update *memory.flags* as needed.
    Returns a one-line observation string fed back to the LLM.
    """
    action_type = action.get("type", "")
    target      = action.get("target", "")

    try:
        if action_type == "fill":
            return _fill(page, target, action.get("value", ""), memory)

        elif action_type == "click":
            return _click(page, target)

        elif action_type == "check":
            return _check(page, target, memory)

        elif action_type == "select":
            return _select(page, target, action.get("option", ""))

        elif action_type == "captcha":
            return _captcha(page, target, memory)

        elif action_type == "navigate":
            return _navigate(page, action.get("url", ""))

        elif action_type == "wait":
            page.wait_for_timeout(2000)
            return f"Waited. Reason: {action.get('reason', '')}"

        elif action_type == "done":
            return f"DONE: {action.get('reason', '')}"

        else:
            return f"Unknown action type: '{action_type}'"

    except Exception as exc:
        return f"ERROR executing {action_type} on '{target}': {exc}"


# =====================================================
# ACTION HANDLERS
# =====================================================

def _fill(page: Page, target: str, value: str, memory: dict) -> str:
    el = _resolve(page, target)
    el.clear()
    el.fill(value)

    # Update flags based on field semantics
    placeholder = (el.get_attribute("placeholder") or "").lower()
    input_type  = (el.get_attribute("type") or "").lower()

    if any(k in placeholder for k in ("username", "email", "mobile", "user")):
        memory["flags"]["username_filled"] = True
    elif "password" in placeholder or input_type == "password":
        memory["flags"]["password_filled"] = True

    safe_value = "***" if input_type == "password" else value
    return f"Filled '{target}' with '{safe_value}'"


_ERROR_PHRASES = [
    "invalid security code",
    "please enter valid",
    "incorrect password",
    "invalid password",
    "invalid username",
    "login failed",
    "authentication failed",
    "wrong captcha",
    "session expired",
    "access denied",
]


def _scan_page_errors(page: Page) -> str:
    """Return the first matching error phrase found in the page body, or empty string."""
    try:
        body = page.locator("body").inner_text().lower()
        for phrase in _ERROR_PHRASES:
            if phrase in body:
                return phrase
    except Exception:
        pass
    return ""


def _click(page: Page, target: str) -> str:
    el = _resolve(page, target)
    # Element is already confirmed visible by _resolve; no scroll needed.
    el.click()
    try:
        page.wait_for_load_state("networkidle", timeout=6000)
    except Exception:
        pass  # some clicks don't trigger navigation

    # Post-click error scan — surfaces validation errors in the observation
    # string so the LLM doesn't have to infer failure from the next step.
    error_hint = _scan_page_errors(page)
    suffix = f" | WARNING PAGE ERROR: \"{error_hint}\"" if error_hint else ""
    return f"Clicked '{target}'{suffix}"


def _check(page: Page, target: str, memory: dict) -> str:
    el = _resolve(page, target)
    el.check()
    memory["flags"]["terms_accepted"] = True
    return f"Checked '{target}'"


def _select(page: Page, target: str, option: str) -> str:
    """
    Handles select2 / aria combobox two-step:
      1. Click the trigger to open the dropdown
      2. Wait for the option list to render
      3. Click the matching option (partial text match, case-insensitive)

    Does NOT fall back to native select_option — select2 elements are not
    <select> tags and select_option always throws on them.
    """
    el = _resolve(page, target)
    el.click()
    # Give select2 time to open and render its option list
    page.wait_for_timeout(800)

    # Strategy 1: exact ARIA role match
    opt = page.get_by_role("option", name=option)
    if opt.count() > 0:
        opt.first.click()
        return f"Selected '{option}' (exact match) via '{target}'"

    # Strategy 2: partial text match via ARIA role (recorded script uses partial names)
    partial = option[:25]  # e.g. "DDA (Delhi Development" → first 25 chars
    opt = page.get_by_role("option", name=partial)
    if opt.count() > 0:
        opt.first.click()
        return f"Selected '{option}' (partial match) via '{target}'"

    # Strategy 3: select2-specific li selector
    opt = page.locator(f"li.select2-results__option:has-text('{partial}')")
    if opt.count() > 0:
        opt.first.click()
        return f"Selected '{option}' (select2 li) via '{target}'"

    # Nothing matched — report clearly so the LLM can retry
    return (
        f"ERROR: option '{option}' not found in dropdown '{target}'. "
        f"Tried exact, partial ('{partial}'), and select2-li selectors. "
        f"Dropdown may still be closed — retry with click then select."
    )


def _captcha(page: Page, target: str, memory: dict) -> str:
    print("\n" + "=" * 52)
    print("  CAPTCHA REQUIRED — please look at the browser")
    print("=" * 52)
    captcha_value = input("  Type the captcha text shown on screen: ").strip()
    el = _resolve(page, target)
    el.clear()
    el.fill(captcha_value)
    memory["flags"]["captcha_filled"] = True
    return f"Captcha filled by user (value hidden)"


def _navigate(page: Page, url: str) -> str:
    page.goto(url)
    page.wait_for_load_state("networkidle")
    return f"Navigated to {url}"


# =====================================================
# ELEMENT RESOLVER
# =====================================================

# Maps the prefix used in observer IDs → CSS selector for Playwright
_SELECTOR_MAP: dict[str, str] = {
    "button":   "button",
    "textbox":  "input[type='text'], input[type='password'], "
                "input[type='email'], input[type='tel'], "
                "input[type='number'], input:not([type])",
    "checkbox": "input[type='checkbox']",
    "select":   ".select2-selection, [role='combobox']",
    "link":     "a",
}


def _resolve(page: Page, element_id: str):
    """
    Convert an observer element ID (e.g. 'link_18') into a Playwright Locator.

    Indexes are counted over VISIBLE elements only, matching how observer.py
    enumerates them.  This avoids the duplicate-nav problem where hidden mobile
    menu items get the same CSS-nth index as the visible desktop links.
    """
    parts = element_id.rsplit("_", 1)
    if len(parts) != 2 or not parts[1].isdigit():
        raise ValueError(f"Cannot resolve element id: '{element_id}'")

    prefix, target_index = parts[0], int(parts[1])

    selector = _SELECTOR_MAP.get(prefix)
    if selector is None:
        raise ValueError(f"Unknown element prefix '{prefix}' in id '{element_id}'")

    # Walk all matching elements, count only the visible ones, return the nth
    all_els = page.locator(selector).all()
    visible_count = 0
    for el in all_els:
        try:
            if not el.is_visible():
                continue
        except Exception:
            continue
        if visible_count == target_index:
            return el
        visible_count += 1

    raise ValueError(
        f"Could not find visible element #{target_index} for prefix '{prefix}' "
        f"(only {visible_count} visible elements matched selector)"
    )