"""P15 deterministic planning, scope, timing and receipt regressions."""
import copy
import json
import unittest
from pathlib import Path

from audit_desk.core import Desk, PlanningError, sha

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads((ROOT / "fixtures/expected-test-only.json").read_text())
EARLY = "2026-09-10T09:00:00Z"
LATE = "2026-09-12T09:00:00Z"


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.desk = Desk()

    def plan(self, cutoff=EARLY, actor="planner_a"):
        return self.desk.plan(actor, "MES-REPORT-A", "2026-08", cutoff)

    def row(self, plan, control):
        return next(r for r in plan["rows"] if r["control_id"] == control)

    def test_policy_revision_validity_is_audit_period_not_latest_doc(self):
        plan = self.plan()
        self.assertEqual([r["policy"]["doc_id"] for r in plan["rows"]],
                         EXPECTED["primary"]["applicable_policy_ids"])
        self.assertEqual(self.row(self.plan(LATE), "ACCESS-01")["policy"]["revision"], "v1")
        self.assertTrue(all(r["assessment_result"] == "unassessed" for r in plan["rows"]))
        self.assertEqual(plan["assessment_result"], "unassessed")

    def test_period_type_completeness_and_requests_stay_separate(self):
        plan = self.plan()
        access = self.row(plan, "ACCESS-01")
        states = {e["doc_id"]: e["planning_state"] for e in access["candidates"]}
        self.assertEqual(states, {"EV-ACCESS-AUG-R1": "planning_candidate",
                                  "EV-ACCESS-JUL-R1": "outside_period"})
        self.assertEqual(self.row(plan, "RESTORE-01")["candidates"][0]["planning_state"],
                         "wrong_artifact_type")
        self.assertEqual(self.row(plan, "CHANGE-01")["candidates"][0]["planning_state"],
                         "wrong_artifact_type")
        inventory = self.row(plan, "INVENTORY-01")["candidates"][0]
        self.assertEqual(inventory["planning_state"], "incomplete_artifact")
        self.assertEqual(inventory["completeness_declaration"], "partial")
        self.assertNotIn("percentage", json.dumps(plan).lower())
        self.assertEqual([r["control_id"] for r in plan["requests"]],
                         EXPECTED["primary"]["request_control_ids"])
        self.assertIn("실제 구현됐는지", next(r for r in plan["requests"]
                                           if r["control_id"] == "CHANGE-01")["question"])

    def test_post_cutoff_revision_does_not_hint_or_erase_early_snapshot(self):
        early, late = self.plan(EARLY), self.plan(LATE)
        self.assertNotIn("EV-INVENTORY-AUG-R2", json.dumps(early))
        self.assertIn("EV-INVENTORY-AUG-R1", json.dumps(early))
        self.assertEqual(self.row(late, "INVENTORY-01")["candidates"][0]["doc_id"],
                         "EV-INVENTORY-AUG-R2")
        self.assertNotIn("EV-INVENTORY-AUG-R1", json.dumps(late))
        self.assertEqual([r["control_id"] for r in late["requests"]],
                         EXPECTED["later"]["request_control_ids"])
        self.assertNotEqual(early["fingerprint"], late["fingerprint"])

    def test_source_details_recheck_cutoff_scope_and_withdrawal(self):
        with self.assertRaises(PlanningError) as got:
            self.desk.source("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             "EV-INVENTORY-AUG-R2")
        self.assertEqual((got.exception.status, got.exception.code),
                         (404, "source_not_available"))
        source = self.desk.source("planner_a", "MES-REPORT-A", "2026-08", LATE,
                                  "EV-INVENTORY-AUG-R2")
        self.assertEqual(source["revision"], 2)
        with self.assertRaises(PlanningError) as got:
            self.desk.source("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             "EV-ACCESS-B-AUG-R1")
        self.assertEqual(got.exception.status, 404)
        self.desk.withdrawn.add("EV-ACCESS-AUG-R1")
        with self.assertRaises(PlanningError) as got:
            self.desk.source("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             "EV-ACCESS-AUG-R1")
        self.assertEqual(got.exception.status, 404)

    def test_role_projection_precedes_plan_sources_and_counts(self):
        plan = self.plan()
        data = json.dumps(plan)
        for forbidden in EXPECTED["primary"]["restricted_ids"]:
            self.assertNotIn(forbidden, data)
        self.assertNotIn("B-AL-0829", data)
        self.assertEqual(self.desk.metadata("planner_a")["services"], ["MES-REPORT-A"])
        self.assertEqual(self.desk.metadata("planner_b")["services"], ["MES-REPORT-B"])
        with self.assertRaises(PlanningError) as got:
            self.desk.plan("planner_a", "MES-REPORT-B", "2026-08", EARLY)
        self.assertEqual(got.exception.status, 403)
        b = self.desk.plan("planner_b", "MES-REPORT-B", "2026-08", EARLY)
        self.assertNotIn("EV-ACCESS-AUG-R1", json.dumps(b))
        self.assertIn("EV-ACCESS-B-AUG-R1", json.dumps(b))

    def test_review_with_open_requests_is_not_effectiveness_decision(self):
        plan = self.plan()
        receipt, created = self.desk.review("planner_a", "MES-REPORT-A", "2026-08",
                                            EARLY, plan["fingerprint"], "미해결 자료 요청을 포함해 계획만 검토함")
        self.assertTrue(created)
        self.assertEqual(receipt["action"], "reviewed_planning_matrix")
        self.assertEqual(receipt["open_request_count"], 3)
        self.assertEqual(receipt["assessment_result"], "unassessed")
        exported = self.desk.export("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                                    receipt["receipt_id"])
        self.assertTrue(exported["not_audit_result"])
        self.assertTrue(exported["not_oscal"])
        self.assertEqual(len(self.desk.history("planner_a", "MES-REPORT-A", "2026-08", EARLY)), 1)

    def test_repeated_review_exact_note_idempotent_changed_note_rejected(self):
        fingerprint = self.plan()["fingerprint"]
        first, created = self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                                          fingerprint, "note A")
        self.assertTrue(created)
        again, created = self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                                          fingerprint, "note A")
        self.assertFalse(created)
        self.assertEqual(again["receipt_id"], first["receipt_id"])
        with self.assertRaises(PlanningError) as got:
            self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             fingerprint, "note B")
        self.assertEqual(got.exception.code, "review_content_changed")
        self.assertEqual(self.desk.history("planner_a", "MES-REPORT-A", "2026-08", EARLY)[0]["note"], "note A")

    def test_cutoff_change_stales_export_and_later_note_not_visible_earlier(self):
        early = self.plan(EARLY)
        late = self.plan(LATE)
        r1, _ = self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                                 early["fingerprint"], "조기 자료만 검토")
        r2, _ = self.desk.review("planner_a", "MES-REPORT-A", "2026-08", LATE,
                                 late["fingerprint"], "EV-INVENTORY-AUG-R2 포함 검토")
        history = self.desk.history("planner_a", "MES-REPORT-A", "2026-08", EARLY)
        self.assertEqual([r["receipt_id"] for r in history], [r1["receipt_id"]])
        self.assertNotIn("EV-INVENTORY-AUG-R2", json.dumps(history))
        with self.assertRaises(PlanningError) as got:
            self.desk.export("planner_a", "MES-REPORT-A", "2026-08", LATE,
                             r1["receipt_id"])
        self.assertEqual(got.exception.code, "stale_receipt")
        with self.assertRaises(PlanningError) as got:
            self.desk.export("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             r2["receipt_id"])
        self.assertEqual(got.exception.code, "stale_receipt")

    def test_withdrawal_invalidates_review_and_export(self):
        original = self.plan()
        receipt, _ = self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                                      original["fingerprint"], "계획 검토")
        self.desk.withdrawn.add("EV-ACCESS-AUG-R1")
        changed = self.plan()
        self.assertNotEqual(changed["fingerprint"], original["fingerprint"])
        self.assertIn("ACCESS-01", [r["control_id"] for r in changed["requests"]])
        self.assertEqual(self.desk.history("planner_a", "MES-REPORT-A", "2026-08", EARLY), [])
        with self.assertRaises(PlanningError) as got:
            self.desk.export("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             receipt["receipt_id"])
        self.assertEqual(got.exception.code, "stale_receipt")

    def test_viewer_cannot_review_or_export(self):
        plan = self.plan(actor="viewer_a")
        self.assertEqual(plan["assessment_result"], "unassessed")
        with self.assertRaises(PlanningError) as got:
            self.desk.review("viewer_a", "MES-REPORT-A", "2026-08", EARLY,
                             plan["fingerprint"], "read-only")
        self.assertEqual(got.exception.status, 403)
        with self.assertRaises(PlanningError) as got:
            self.desk.export("viewer_a", "MES-REPORT-A", "2026-08", EARLY,
                             "missing")
        self.assertEqual(got.exception.status, 403)

    def test_same_revision_conflict_holds_without_valid_candidate(self):
        current = next(e for e in self.desk.evidence
                       if e["doc_id"] == "EV-INVENTORY-AUG-R1")
        other = copy.deepcopy(current)
        other["doc_id"] = "EV-INVENTORY-AUG-R1-CONFLICT"
        other["text"] = "서로 다른 동판본 모의 기록"
        other["source_hash"] = sha({k: v for k, v in other.items() if k != "source_hash"})
        self.desk.evidence.append(other)
        plan = self.plan()
        self.assertEqual(plan["plan_status"], "hold_source_or_policy")
        self.assertEqual(self.row(plan, "INVENTORY-01")["candidates"], [])
        self.assertIn("source_revision_conflict",
                      [r["reason_code"] for r in plan["requests"]])
        with self.assertRaises(PlanningError) as got:
            self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             plan["fingerprint"], "검토")
        self.assertEqual(got.exception.code, "plan_on_hold")

    def test_policy_withdrawal_blocks_completeness_and_export(self):
        original = self.plan()
        receipt, _ = self.desk.review("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                                      original["fingerprint"], "검토")
        self.desk.withdrawn.add("POL-ACCESS-01-V1")
        changed = self.plan()
        self.assertEqual(self.row(changed, "ACCESS-01")["policy_issue"],
                         "policy_gap_or_overlap")
        with self.assertRaises(PlanningError) as got:
            self.desk.export("planner_a", "MES-REPORT-A", "2026-08", EARLY,
                             receipt["receipt_id"])
        self.assertEqual(got.exception.code, "stale_receipt")


if __name__ == "__main__":
    unittest.main()
