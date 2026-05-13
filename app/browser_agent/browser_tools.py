"""
browser_tools.py  —  Playwright browser factory.
"""

from playwright.sync_api import sync_playwright


def start_browser(headless: bool = False):
    """
    Launch a Chromium browser and return
    (playwright, browser, context, page).

    Keep headless=False so the user can see the CAPTCHA and
    watch the agent work.
    """
    playwright = sync_playwright().start()

    browser = playwright.chromium.launch(
        headless=headless,
        args=["--start-maximized"],
    )

    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )

    page = context.new_page()

    return playwright, browser, context, page