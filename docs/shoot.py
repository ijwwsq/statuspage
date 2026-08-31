"""Capture real screenshots of the running demo for the README.
Prereqs:  the demo must be running on http://localhost:8090
          pip install playwright && playwright install chromium
Run from the repo root:  python docs/shoot.py
"""
from playwright.sync_api import sync_playwright

URL = "http://localhost:8090"
W = 960


def shoot():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme, top_name in (("light", "docs/screenshot-light.png"),
                                ("dark", "docs/screenshot-dark.png")):
            ctx = browser.new_context(viewport={"width": W, "height": 900},
                                      device_scale_factor=2, color_scheme=theme)
            page = ctx.new_page()
            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector(".group .component", timeout=15000)
            page.wait_for_selector(".cal-wrap", timeout=15000)
            page.wait_for_timeout(500)  # let uptime bars/calendar settle
            # cropped hero (top of page)
            page.screenshot(path=top_name, clip={"x": 0, "y": 0, "width": W, "height": 880})
            # full page (light only — used as the wide shot below the pair)
            if theme == "light":
                page.screenshot(path="docs/screenshot-full.png", full_page=True)
            ctx.close()
        browser.close()
    print("wrote docs/screenshot-light.png, docs/screenshot-dark.png, docs/screenshot-full.png")


if __name__ == "__main__":
    shoot()
