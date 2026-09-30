"""Frozen P15 synthetic input checks. No runtime/model access to expected file."""
import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


class FixtureContractTests(unittest.TestCase):
    def test_manifest_and_source_hashes(self):
        manifest = json.loads((FIX / "manifest.json").read_text())
        self.assertEqual(manifest["runtime_input"], ["scope.json", "policies.json", "evidence.json"])
        self.assertEqual(manifest["test_only"], ["expected-test-only.json"])
        for name, digest in manifest["sha256"].items():
            self.assertEqual(hashlib.sha256((FIX / name).read_bytes()).hexdigest(), digest)
        for name in ("policies.json", "evidence.json"):
            for row in json.loads((FIX / name).read_text()):
                body = {k: v for k, v in row.items() if k != "source_hash"}
                self.assertEqual(hashlib.sha256(canonical(body)).hexdigest(), row["source_hash"])

    def test_august_contract_frozen_before_model(self):
        scope = json.loads((FIX / "scope.json").read_text())
        policies = json.loads((FIX / "policies.json").read_text())
        evidence = json.loads((FIX / "evidence.json").read_text())
        self.assertEqual((scope["period_start"], scope["period_end_exclusive"]),
                         ("2026-08-01", "2026-09-01"))
        self.assertEqual(scope["planning_cutoff"], "2026-09-10T09:00:00Z")
        self.assertEqual(len(policies), 7)
        self.assertEqual(len(evidence), 7)
        self.assertEqual({p["control_id"] for p in policies if p["site"] == "PLANT-A"},
                         {"ACCESS-01", "RESTORE-01", "CHANGE-01", "INVENTORY-01"})
        self.assertEqual({e["doc_id"] for e in evidence if e["site"] == "PLANT-B"},
                         {"EV-ACCESS-B-AUG-R1"})


if __name__ == "__main__":
    unittest.main()
