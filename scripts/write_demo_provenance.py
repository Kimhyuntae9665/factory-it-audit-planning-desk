"""Hash only the actual local browser media; no media regeneration or model calls."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
demo = root / "artifacts" / "demo"
checks = json.loads((demo / "browser-checks.json").read_text())
media = [demo / name for name in checks["screenshots"] + [checks["video"]]]
receipt = {
    "capture": "Google Chrome headless, real loopback P15 UI, frozen fictional sources",
    "reference": "P09 v2 development screenshot",
    "reference_url": "https://github.com/Kimhyuntae9665/maintenance-job-plan-draft-review/blob/main/artifacts/media/v2-development-stored-desktop.png",
    "model_calls": 0,
    "browser_check_count": len(checks["checks"]),
    "browser_checks": checks["checks"],
    "media": [
        {"path": str(path.relative_to(root)).replace("\\", "/"),
         "size_bytes": path.stat().st_size,
         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in media
    ],
}
(demo / "provenance.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("hashed_media", len(media), "browser_checks", len(checks["checks"]))
