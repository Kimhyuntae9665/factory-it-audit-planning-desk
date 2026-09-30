"""Narrow live-browser recapture after the source body and hash have loaded."""
import hashlib
import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audit_desk.core import CUTOFFS, Desk
from audit_desk.server import make_server

OUT = ROOT / "artifacts" / "demo"
DOC_ID = "EV-INVENTORY-AUG-R1"


def main():
    from playwright.sync_api import sync_playwright

    desk = Desk()
    expected = desk.source("planner_a", "MES-REPORT-A", "2026-08", CUTOFFS[0], DOC_ID)
    server = make_server(port=0, desk=desk)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/google-chrome", headless=True,
                args=["--disable-gpu"])
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=1, is_mobile=True, has_touch=True)
            page = context.new_page()
            page.goto("http://127.0.0.1:" + str(server.server_port),
                      wait_until="domcontentloaded")
            page.locator("#matrixBody tr").first.wait_for()
            page.get_by_role("button", name=DOC_ID).click()
            page.locator("#sourceDialog[open]").wait_for()
            page.wait_for_function("""({id, hash}) => {
              const body = document.querySelector('#sourceText')?.textContent || '';
              return body.includes(id) && body.includes(hash);
            }""", arg={"id": DOC_ID, "hash": expected["source_hash"]})
            displayed = json.loads(page.locator("#sourceText").inner_text())
            assert displayed["doc_id"] == DOC_ID
            assert displayed["source_hash"] == expected["source_hash"]
            assert displayed["text"] == expected["text"] and displayed["text"]
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
            path = OUT / "09-mobile-source.png"
            page.screenshot(path=str(path))
            receipt = {
                "capture": "actual live Chrome 390px source dialog after body loaded",
                "doc_id": DOC_ID,
                "source_hash": expected["source_hash"],
                "exact_body_match": True,
                "screen_width": 390,
                "screenshot": path.name,
                "screenshot_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            (OUT / "mobile-source-check.json").write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(json.dumps(receipt, ensure_ascii=False))
            context.close()
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    main()
