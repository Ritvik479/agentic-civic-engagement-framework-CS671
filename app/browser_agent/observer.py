"""
Observer module — extracts interactive elements from the current page
and returns them as a list of dicts (used by the planner).
"""


def extract_elements(page) -> list[dict]:
    elements: list[dict] = []

    # =====================================================
    # BUTTONS
    # =====================================================

    visible_i = 0
    for b in page.locator("button").all():
        try:
            if not b.is_visible():
                continue
            text = b.inner_text().strip()
            if not text:
                continue
            elements.append({
                "id":   f"button_{visible_i}",
                "type": "button",
                "text": text,
            })
            visible_i += 1
        except Exception:
            pass

    # =====================================================
    # TEXT INPUTS  (excludes checkboxes / radios)
    # =====================================================

    text_selector = (
        "input[type='text'], input[type='password'], "
        "input[type='email'], input[type='tel'], "
        "input[type='number'], input:not([type])"
    )

    visible_i = 0
    for t in page.locator(text_selector).all():
        try:
            if not t.is_visible():
                continue
            elements.append({
                "id":          f"textbox_{visible_i}",
                "type":        "textbox",
                "placeholder": t.get_attribute("placeholder") or "",
                "input_type":  t.get_attribute("type") or "text",
                "name":        t.get_attribute("name") or "",
            })
            visible_i += 1
        except Exception:
            pass

    # =====================================================
    # CHECKBOXES
    # =====================================================

    visible_i = 0
    for c in page.locator("input[type='checkbox']").all():
        try:
            if not c.is_visible():
                continue
            cb_id    = c.get_attribute("id") or ""
            label    = ""
            if cb_id:
                try:
                    label = page.locator(f"label[for='{cb_id}']").inner_text().strip()
                except Exception:
                    pass
            elements.append({
                "id":      f"checkbox_{visible_i}",
                "type":    "checkbox",
                "label":   label,
                "checked": c.is_checked(),
            })
            visible_i += 1
        except Exception:
            pass

    # =====================================================
    # SELECT2 / COMBOBOX DROPDOWNS
    # =====================================================

    visible_i = 0
    for s in page.locator(".select2-selection, [role='combobox']").all():
        try:
            if not s.is_visible():
                continue
            label = s.inner_text().strip() or s.get_attribute("aria-label") or ""
            elements.append({
                "id":    f"select_{visible_i}",
                "type":  "select",
                "label": label,
            })
            visible_i += 1
        except Exception:
            pass

    # =====================================================
    # ALERTS — tagged by severity so the LLM can tell errors from info banners
    # =====================================================
    #
    # severity="error"  → blocking; must be resolved before proceeding
    # severity="info"   → advisory/informational; safe to ignore and proceed
    #
    # Bootstrap class map:
    #   alert-danger / alert-error  → error
    #   alert-warning               → warning (treated as error)
    #   alert-info / alert-success  → info (safe to ignore)
    #   bare .alert with no subclass → info (assume non-blocking)

    _SEVERITY_MAP = {
        "alert-danger":  "error",
        "alert-error":   "error",
        "alert-warning": "warning",
        "alert-info":    "info",
        "alert-success": "info",
    }

    # Only error/validation selectors — not generic .alert which catches info banners
    error_selectors = (
        ".alert-danger, .alert-error, .alert-warning, "
        ".error, .error-msg, .validation-error, "
        ".field-validation-error, span.text-danger, div.text-danger, "
        "[class*='invalid']:not(input):not(select):not(textarea)"
    )
    info_selectors = ".alert-info, .alert-success"

    # Keywords that make an alert advisory regardless of CSS class.
    # These are government site banners that warn about scope, not form errors.
    _INFO_KEYWORDS = [
        "pension", "lodge pension", "ministry/department",
        "dopt", "click here", "pertaining to any ministry",
    ]

    def _is_advisory(text: str) -> bool:
        t = text.lower()
        return any(kw in t for kw in _INFO_KEYWORDS)

    seen_alerts: set[str] = set()

    def _collect_alerts(selector: str, default_severity: str) -> None:
        for a in page.locator(selector).all():
            try:
                if not a.is_visible():
                    continue
                text = a.inner_text().strip()
                if not text or text in seen_alerts:
                    continue
                seen_alerts.add(text)
                # Demote to info if text matches advisory keywords,
                # regardless of which CSS class triggered collection.
                severity = "info" if _is_advisory(text) else default_severity
                elements.append({
                    "id":       f"alert_{len(seen_alerts)}",
                    "type":     "alert",
                    "severity": severity,
                    "text":     text,
                })
            except Exception:
                pass

    _collect_alerts(error_selectors, "error")
    _collect_alerts(info_selectors,  "info")

    # =====================================================
    # CURRENT PAGE CONTEXT  (URL + title — helps LLM know if login succeeded)
    # =====================================================

    try:
        current_url   = page.url
        current_title = page.title()
        elements.append({
            "id":    "page_context_0",
            "type":  "page_context",
            "url":   current_url,
            "title": current_title,
        })
    except Exception:
        pass

    # =====================================================
    # LINKS
    # =====================================================

    visible_i = 0
    seen_link_texts: set[str] = set()
    for l in page.locator("a").all():
        try:
            if not l.is_visible():
                continue
            text = l.inner_text().strip()
            if not text or text in seen_link_texts:
                continue
            seen_link_texts.add(text)
            elements.append({
                "id":   f"link_{visible_i}",
                "type": "link",
                "text": text,
            })
            visible_i += 1
        except Exception:
            pass

    # =====================================================
    # PAGE TEXT  (alerts, headings, error messages)
    # =====================================================

    try:
        body_text = page.locator("body").inner_text()
        seen: set[str] = set()
        important: list[str] = []

        for line in body_text.split("\n"):
            line = line.strip()
            if len(line) < 4 or line in seen:
                continue
            seen.add(line)
            important.append(line)

        elements.append({
            "id":      "page_text_0",
            "type":    "page_text",
            "content": important[:30],
        })
    except Exception as exc:
        print(f"[OBSERVER] Page text error: {exc}")

    return elements