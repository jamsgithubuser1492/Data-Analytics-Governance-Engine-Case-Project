"""Rebuild the README screenshots and the walkthrough GIF from the public demo, so they never go stale.

Usage:  python scripts/make_screenshots.py        (needs requirements-dev.txt and the preinstalled Chromium)
"""
from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img"
PORT = int(os.environ.get("SHOT_PORT", "8765"))
BASE = f"http://localhost:{PORT}"
CHROMIUM = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")


def wait_healthy() -> None:
    for _ in range(60):
        try:
            if urllib.request.urlopen(f"{BASE}/_stcore/health", timeout=2).read() == b"ok":
                return
        except Exception:
            time.sleep(1)
    raise RuntimeError("the app did not start")


def settle(pg, ms: int = 2500) -> None:
    pg.wait_for_selector("h1, h2, h3", timeout=60000)
    pg.wait_for_timeout(ms)


def scroll_to(pg, text: str) -> None:
    pg.get_by_text(text, exact=False).first.scroll_into_view_if_needed()
    pg.wait_for_timeout(900)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "MMGE_DEMO_MODE": "1", "MMGE_DATA_DIR": tempfile.mkdtemp()}
    server = subprocess.Popen([sys.executable, "-m", "streamlit", "run", "app/app.py", "--server.headless=true", f"--server.port={PORT}"],
                              cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frames = []
    try:
        wait_healthy()
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=CHROMIUM if Path(CHROMIUM).exists() else None)

            def page(width=1440, height=900, scheme="light"):
                return browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme).new_page()

            def snap(pg, name, keep=False):
                data = pg.screenshot()
                (OUT / name).write_bytes(data)
                if keep:
                    frames.append(Image.open(io.BytesIO(data)).convert("RGB").resize((960, 600)))

            pg = page()
            pg.goto(BASE); settle(pg, 9000)
            snap(pg, "01_dashboard.png", keep=True)
            pg.get_by_role("tab", name="CFO / Finance").first.click() if pg.get_by_role("tab", name="CFO / Finance").count() else pg.get_by_text("CFO / Finance").first.click()
            pg.wait_for_timeout(3500); scroll_to(pg, "Capital destruction leaderboard"); snap(pg, "01b_cfo_view.png", keep=True)
            pg.get_by_text("Everyone").first.click(); pg.wait_for_timeout(2500)
            scroll_to(pg, "The advisory council"); snap(pg, "02_council.png", keep=True)
            scroll_to(pg, "The charts behind the answer")
            if pg.get_by_text("Table", exact=True).count():
                pg.get_by_text("Table", exact=True).first.click(); pg.wait_for_timeout(1500)
            snap(pg, "03_chart_table.png", keep=True)
            scroll_to(pg, "Decisions for your sign-off"); snap(pg, "03b_decisions.png", keep=True)
            pg.goto(f"{BASE}/Signoff"); settle(pg, 4500); snap(pg, "04_signoff.png", keep=True)
            pg.goto(f"{BASE}/Strategy"); settle(pg, 4500); snap(pg, "05_strategy.png", keep=True)
            pg.goto(f"{BASE}/Research"); settle(pg, 4500); snap(pg, "05b_research.png")
            dark = page(scheme="dark"); dark.goto(BASE); settle(dark, 8000); snap(dark, "06_dashboard_dark.png")
            phone = page(390, 844); phone.goto(BASE); settle(phone, 8000); snap(phone, "07_dashboard_mobile.png")
            browser.close()
    finally:
        server.terminate()
    if frames:
        frames[0].save(OUT / "walkthrough.gif", save_all=True, append_images=frames[1:], duration=2200, loop=0, optimize=True)
        print("wrote", len(frames), "frame GIF,", round((OUT / "walkthrough.gif").stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
