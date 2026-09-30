"""Actual headless Chrome workflow checks and unaltered P15 demo captures."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit_desk.core import Desk
from audit_desk.server import make_server

OUT = ROOT / "artifacts" / "demo"
RAW = OUT / "raw"
EARLY = "2026-09-10T09:00:00Z"
LATE = "2026-09-12T09:00:00Z"


class DelayedSourceDesk(Desk):
    def __init__(self):
        super().__init__()
        self.delay_id = None
        self.source_started = threading.Event()
        self.source_release = threading.Event()

    def source(self, actor_id, service, period, cutoff, doc_id):
        if doc_id == self.delay_id:
            self.delay_id = None
            self.source_started.set()
            if not self.source_release.wait(timeout=10):
                raise RuntimeError("delayed_source_test_timeout")
        return super().source(actor_id, service, period, cutoff, doc_id)


def capture():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    # Playwright's video helper is absent, while system ffmpeg is already installed.
    # Point a process-local browser cache at the existing binary; no download/install.
    browser_cache = RAW / "pw-browsers"
    ffmpeg_link = browser_cache / "ffmpeg-1011" / "ffmpeg-linux"
    ffmpeg_link.parent.mkdir(parents=True, exist_ok=True)
    if not ffmpeg_link.exists():
        ffmpeg_link.symlink_to("/usr/bin/ffmpeg")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browser_cache)
    from playwright.sync_api import sync_playwright
    desk = DelayedSourceDesk()
    server = make_server(port=0, desk=desk)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = "http://127.0.0.1:" + str(server.server_port)
    checks = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/google-chrome", headless=True,
                args=["--disable-gpu"])
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                device_scale_factor=1,
                record_video_dir=str(RAW),
                record_video_size={"width": 1440, "height": 900},
                accept_downloads=True)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            page.locator("#matrixBody tr").first.wait_for()
            assert page.locator("#matrixBody tr").count() == 4
            assert page.locator("#requestCount").inner_text() == "3"
            assert "EV-INVENTORY-AUG-R2" not in page.locator("body").inner_text()
            assert page.locator("#planState").inner_text() == "계획 검토 가능"
            checks.append("early cutoff: v1 policy, 4 rows, 3 requests, no future R2")
            page.screenshot(path=str(OUT / "01-desktop-august-matrix.png"))

            policy = page.get_by_role("button", name="v1 · monthly · 승인 적용").first
            policy.focus()
            policy.press("Enter")
            page.locator("#sourceDialog[open]").wait_for()
            assert "POL-ACCESS-01-V1" in page.locator("#sourceText").inner_text()
            page.screenshot(path=str(OUT / "02-policy-source-drawer.png"))
            page.keyboard.press("Escape")
            assert policy.evaluate("(el) => document.activeElement === el")
            checks.append("keyboard source dialog: exact v1 source and focus return")

            backup = page.get_by_role("button", name="EV-BACKUP-AUG-R1")
            backup.click()
            page.locator("#sourceDialog[open]").wait_for()
            assert "복원 연습 또는 복원 결과는 기록하지 않는다" in page.locator("#sourceText").inner_text()
            page.screenshot(path=str(OUT / "03-backup-not-restore.png"))
            page.keyboard.press("Escape")

            page.locator("#reviewNote").fill("미해결 자료 요청 3건을 포함해 계획만 검토함")
            page.get_by_role("button", name="검토한 계획 기록").click()
            page.get_by_role("button", name="검토한 계획 JSON 받기").wait_for()
            assert "효과성 미평가" in page.locator("#reviewHistory").inner_text()
            page.screenshot(path=str(OUT / "04-reviewed-plan-history.png"))
            with page.expect_download() as download_info:
                page.get_by_role("button", name="검토한 계획 JSON 받기").click()
            download = download_info.value
            exported = json.loads(Path(download.path()).read_text())
            assert exported["not_audit_result"] is True
            assert exported["not_oscal"] is True
            assert exported["plan"]["assessment_result"] == "unassessed"
            checks.append("review/export: exact current receipt and unassessed result")

            page.locator("#cutoff").select_option(LATE)
            page.get_by_role("button", name="EV-INVENTORY-AUG-R2").wait_for()
            assert page.locator("#requestCount").inner_text() == "2"
            assert page.get_by_role("button", name="검토한 계획 JSON 받기").count() == 0
            page.screenshot(path=str(OUT / "05-later-revision-stale-review.png"))
            checks.append("later cutoff: R2 selected, 2 requests, prior review absent")

            page.locator("#cutoff").select_option(EARLY)
            page.get_by_role("button", name="EV-INVENTORY-AUG-R1").wait_for()
            assert "EV-INVENTORY-AUG-R2" not in page.locator("body").inner_text()
            page.get_by_role("button", name="검토한 계획 JSON 받기").wait_for()
            page.screenshot(path=str(OUT / "06-return-early-history.png"))
            checks.append("return to early cutoff: no future R2; scoped receipt restored")

            page.locator("#actor").select_option("viewer_a")
            page.locator("#matrixBody tr").first.wait_for()
            assert page.locator("#reviewButton").is_disabled()
            page.screenshot(path=str(OUT / "07-readonly-role.png"))
            checks.append("viewer cannot submit review")

            mobile = browser.new_context(viewport={"width": 390, "height": 844},
                device_scale_factor=1, is_mobile=True, has_touch=True)
            phone = mobile.new_page()
            phone.goto(url, wait_until="domcontentloaded")
            phone.locator("#matrixBody tr").first.wait_for()
            assert phone.locator("#matrixBody tr").count() == 4
            assert phone.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            assert phone.locator("h1").evaluate("(el) => el.scrollWidth <= el.clientWidth + 1")
            phone.screenshot(path=str(OUT / "08-mobile-390-matrix.png"), full_page=True)
            phone.get_by_role("button", name="EV-INVENTORY-AUG-R1").click()
            phone.locator("#sourceDialog[open]").wait_for()
            phone.screenshot(path=str(OUT / "09-mobile-source.png"))
            checks.append("390px mobile matrix/source: no document overflow")
            mobile.close()

            race = context.new_page()
            race.goto(url, wait_until="domcontentloaded")
            race.locator("#matrixBody tr").first.wait_for()
            desk.delay_id = "POL-ACCESS-01-V1"
            race.get_by_role("button", name="v1 · monthly · 승인 적용").first.click()
            assert desk.source_started.wait(timeout=5)
            race.keyboard.press("Escape")
            race.get_by_role("button", name="v2 원문").first.click()
            race.locator("#sourceText").get_by_text("POL-ACCESS-01-V2").wait_for()
            with race.expect_response(lambda response:
                    "/api/source/POL-ACCESS-01-V1" in response.url):
                desk.source_release.set()
            assert race.locator("#sourceTitle").inner_text().endswith("POL-ACCESS-01-V2")
            assert "POL-ACCESS-01-V2" in race.locator("#sourceText").inner_text()
            assert "POL-ACCESS-01-V1" not in race.locator("#sourceText").inner_text()
            race.keyboard.press("Escape")
            checks.append("delayed A source cannot replace later B title/body/hash")

            race.locator("#cutoff").select_option(LATE)
            race.get_by_role("button", name="EV-INVENTORY-AUG-R2").wait_for()
            race.locator("#reviewNote").fill("later R2 note for two requests")
            race.locator("#cutoff").select_option(EARLY)
            race.get_by_role("button", name="EV-INVENTORY-AUG-R1").wait_for()
            assert race.locator("#reviewNote").input_value() == ""
            checks.append("cutoff change clears unbound review draft")

            race.locator("#period").select_option("2026-07")
            race.locator("#cutoff").select_option(LATE)
            race.locator("#matrixBody tr").first.wait_for()
            assert "7월" in race.locator("#requestList").inner_text()
            assert "8월 복원" not in race.locator("#requestList").inner_text()
            race.screenshot(path=str(OUT / "10-july-period.png"))
            race.locator("#reviewNote").fill("July late draft")
            race.locator("#actor").select_option("viewer_a")
            race.locator("#matrixBody tr").first.wait_for()
            assert race.locator("#period").input_value() == "2026-07"
            assert race.locator("#cutoff").input_value() == LATE
            assert race.locator("#reviewNote").input_value() == ""
            assert race.locator("#reviewButton").is_disabled()
            checks.append("role change preserves valid July/later filters and clears review draft")
            race.close()

            video_path = page.video.path()
            context.close()
            browser.close()
        output = OUT / "workflow.mp4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video_path),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags",
                        "+faststart", str(output)], check=True, timeout=90)
        report = {"browser": "Google Chrome headless via installed Playwright",
                  "source": "actual loopback 127.0.0.1 UI and frozen synthetic fixture",
                  "no_model_calls": True, "checks": checks,
                  "screenshots": sorted(p.name for p in OUT.glob("*.png")),
                  "video": output.name,
                  "video_bytes": output.stat().st_size}
        (OUT / "browser-checks.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + chr(10))
        print(json.dumps(report, ensure_ascii=False))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    capture()
