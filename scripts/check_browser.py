"""Exercise the real dashboard and portfolio in Chromium, including mobile layout."""

from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
output = root / "docs/screenshots"
output.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    local = Path.home() / "AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe"
    browser = p.chromium.launch(
        executable_path=str(local) if local.exists() else None, headless=True
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1050}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8821", wait_until="networkidle")
    page.get_by_role("button", name="Run backtest").click()
    page.get_by_text("Portfolio equity", exact=True).wait_for(timeout=120000)
    page.get_by_role("status").wait_for(state="hidden", timeout=30000)
    page.screenshot(path=str(output / "research.png"), full_page=True)
    page.get_by_role("button", name="Market data", exact=True).click()
    page.get_by_role("button", name="Load market data").click()
    page.locator("canvas").first.wait_for(timeout=30000)
    page.screenshot(path=str(output / "market.png"), full_page=True)
    page.get_by_role("button", name="Experiments", exact=True).click()
    page.get_by_role("button", name="Open", exact=True).first.wait_for()
    page.get_by_role("button", name="Paper accounts", exact=True).click()
    page.get_by_role("button", name="Create paper account").click()
    page.get_by_role("button", name="Advance ledger").last.wait_for()
    page.get_by_role("button", name="Advance ledger").last.click()
    page.wait_for_function("document.body.innerText.includes('2025-12-31')", timeout=60000)
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Research", exact=True).click()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
    page.screenshot(path=str(output / "mobile.png"), full_page=True)
    page.goto(
        "http://127.0.0.1:8790/work/quantitative-finance-analytics/", wait_until="networkidle"
    )
    page.get_by_text("Explore the evidence.", exact=True).wait_for()
    page.get_by_label("Experiment", exact=True).select_option("3")
    assert page.get_by_text(
        "Synthetic prices for engineering validation.", exact=False
    ).is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
    page.set_viewport_size({"width": 1440, "height": 1050})
    page.screenshot(path=str(output / "portfolio.png"), full_page=True)
    assert not errors, errors
    browser.close()
print("Browser checks passed: research, prices, history, paper replay, mobile, portfolio")
