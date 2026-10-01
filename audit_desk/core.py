"""Synthetic factory-IT audit planning. Never tests control effectiveness."""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
RULES_VERSION = "AUDIT-PLAN-RULES-v1"
CONTROL_ORDER = ("ACCESS-01", "RESTORE-01", "CHANGE-01", "INVENTORY-01")
PERIODS = {"2026-08": ("2026-08-01", "2026-09-01"),
           "2026-07": ("2026-07-01", "2026-08-01")}
CUTOFFS = ("2026-09-10T09:00:00Z", "2026-09-12T09:00:00Z")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone_required")
    return parsed.astimezone(timezone.utc)


class PlanningError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


class Desk:
    def __init__(self, fixture_root=FIX):
        fixture_root = Path(fixture_root)
        manifest = json.loads((fixture_root / "manifest.json").read_text(encoding="utf-8"))
        expected = manifest["sha256"]
        for name in manifest["runtime_input"]:
            actual = hashlib.sha256((fixture_root / name).read_bytes()).hexdigest()
            if actual != expected[name]:
                raise PlanningError("fixture_hash_changed", 500)
        self.scope = json.loads((fixture_root / "scope.json").read_text(encoding="utf-8"))
        self.policies = json.loads((fixture_root / "policies.json").read_text(encoding="utf-8"))
        self.evidence = json.loads((fixture_root / "evidence.json").read_text(encoding="utf-8"))
        for row in self.policies + self.evidence:
            original = {k: v for k, v in row.items() if k != "source_hash"}
            if sha(original) != row["source_hash"]:
                raise PlanningError("source_hash_changed", 500)
        self.withdrawn = set()
        self.reviews = {}
        self._lock = threading.RLock()

    def _actor(self, actor_id):
        actor = self.scope["actors"].get(actor_id)
        if actor is None:
            raise PlanningError("demo_actor_required", 401)
        return {"id": actor_id, **actor}

    def _context(self, actor_id, service, period, cutoff):
        actor = self._actor(actor_id)
        if period not in PERIODS or cutoff not in CUTOFFS:
            raise PlanningError("unsupported_context", 400)
        services = {p["service"] for p in self.policies if p["site"] == actor["site"]}
        if service not in services:
            raise PlanningError("scope_not_available", 403)
        return actor, PERIODS[period], instant(cutoff)

    def metadata(self, actor_id):
        actor = self._actor(actor_id)
        return {"actor_id": actor["id"], "site": actor["site"],
                "can_review": actor["can_review"],
                "services": sorted({p["service"] for p in self.policies
                                    if p["site"] == actor["site"]}),
                "periods": list(PERIODS), "cutoffs": list(CUTOFFS),
                "identity_notice": "Demo actor selector; not authentication or SSO."}

    def _admitted(self, rows, site, service, cutoff):
        # Site/service, availability and global withdrawal precede revision links.
        return [r for r in rows if r["site"] == site and r["service"] == service
                and instant(r["available_at"]) <= cutoff and r["doc_id"] not in self.withdrawn]

    @staticmethod
    def _current_evidence(admitted):
        groups = defaultdict(list)
        for row in admitted:
            groups[row["logical_id"]].append(row)
        current, conflicts = [], []
        for logical_id, versions in groups.items():
            latest = max(v["revision"] for v in versions)
            peers = [v for v in versions if v["revision"] == latest]
            hashes = {v["source_hash"] for v in peers}
            if len(hashes) != 1:
                conflicts.append(logical_id)
                continue
            current.append(peers[0])
        return current, conflicts

    @staticmethod
    def _applicable_policy(rows, start, end):
        valid = [p for p in rows if p["status"] == "approved"
                 and p["effective_from"] <= start
                 and (p["effective_until"] is None or p["effective_until"] >= end)]
        if len(valid) != 1:
            return None, "policy_gap_or_overlap"
        return valid[0], None

    def plan(self, actor_id, service, period="2026-08", cutoff=CUTOFFS[0]):
        actor, (start, end), cutoff_dt = self._context(actor_id, service, period, cutoff)
        month_label = str(int(period[-2:])) + "월"
        policy_docs = self._admitted(self.policies, actor["site"], service, cutoff_dt)
        evidence_docs = self._admitted(self.evidence, actor["site"], service, cutoff_dt)
        current, conflicts = self._current_evidence(evidence_docs)
        rows, requests = [], []
        for control_id in CONTROL_ORDER:
            policies = [p for p in policy_docs if p["control_id"] == control_id]
            policy, policy_issue = self._applicable_policy(policies, start, end)
            candidates = []
            for e in current:
                if e["control_hint"] != control_id:
                    continue
                period_match = start <= e["event_date"] < end
                type_match = bool(policy and e["evidence_type"] == policy["required_evidence_type"])
                missing_fields = ([f for f in policy["required_fields"]
                                   if e["fields"].get(f) in (None, "")]
                                  if policy else [])
                declaration = e["completeness"]
                declared_sufficient = declaration in ("declared_complete", "declared_full")
                if not period_match:
                    state = "outside_period"
                elif not type_match:
                    state = "wrong_artifact_type"
                elif missing_fields or not declared_sufficient:
                    state = "incomplete_artifact"
                else:
                    state = "planning_candidate"
                candidates.append({
                    "doc_id": e["doc_id"], "source_hash": e["source_hash"],
                    "available_at": e["available_at"], "event_date": e["event_date"],
                    "evidence_type": e["evidence_type"], "period_match": period_match,
                    "type_match": type_match, "missing_fields": missing_fields,
                    "completeness_declaration": declaration,
                    "planning_state": state, "assessment_result": "unassessed"})
            candidates.sort(key=lambda x: x["doc_id"])
            if policy_issue:
                requests.append({"control_id": control_id, "reason_code": policy_issue,
                                 "question": "해당 기간에 승인되어 적용되는 정책 판본을 확인해 주세요."})
            elif not any(c["planning_state"] == "planning_candidate" for c in candidates):
                questions = {
                    "ACCESS-01": f"{month_label} 특권 계정 검토의 검토자 역할·검토일·계정 목록 판본을 요청합니다.",
                    "RESTORE-01": f"{month_label} 복원 연습일과 문서화된 결과를 요청합니다. 백업 완료 요약은 다른 자료입니다.",
                    "CHANGE-01": "계획 변경이 실제 구현됐는지 확인하고, 구현됐다면 변경 요청·승인·구현 기록을 요청합니다.",
                    "INVENTORY-01": f"{month_label} 서비스 전체 범위의 구성요소 내보내기와 범위·완전성 선언을 요청합니다."}
                requests.append({"control_id": control_id, "reason_code": "planning_evidence_gap",
                                 "question": questions[control_id]})
            alternatives = [
                {"doc_id": p["doc_id"], "source_hash": p["source_hash"],
                 "revision": p["revision"], "status": p["status"],
                 "effective_from": p["effective_from"],
                 "exclusion": ("not_approved_draft" if p["status"] != "approved"
                               else "outside_audit_period")}
                for p in policies if policy is None or p["doc_id"] != policy["doc_id"]]
            rows.append({
                "control_id": control_id,
                "policy": ({"doc_id": policy["doc_id"], "source_hash": policy["source_hash"],
                            "revision": policy["revision"], "cadence": policy["cadence"],
                            "clause": policy["clause"], "validity": "approved_applicable"}
                           if policy else None),
                "policy_alternatives": alternatives,
                "policy_issue": policy_issue, "candidates": candidates,
                "assessment_result": "unassessed"})
        conflict_hints = sorted(set(conflicts))
        if conflict_hints:
            requests.append({"control_id": None, "reason_code": "source_revision_conflict",
                             "question": "동일 판본 증거의 내용 충돌을 출처 담당자에게 확인해 주세요."})
        plan_status = ("hold_source_or_policy" if conflict_hints or any(r["policy_issue"] for r in rows)
                       else "ready_for_planning_review")
        projected = {"rules_version": RULES_VERSION, "actor_id": actor["id"],
                     "role_site": actor["site"], "service": service, "period": period,
                     "period_start": start, "period_end_exclusive": end, "cutoff": cutoff,
                     "rows": rows, "requests": requests, "plan_status": plan_status,
                     "assessment_result": "unassessed"}
        projected["fingerprint"] = sha(projected)
        return projected

    def source(self, actor_id, service, period, cutoff, doc_id):
        actor, _, cutoff_dt = self._context(actor_id, service, period, cutoff)
        admitted = self._admitted(self.policies + self.evidence,
                                 actor["site"], service, cutoff_dt)
        for row in admitted:
            if row["doc_id"] == doc_id:
                return row
        # One response for unknown, other site, unavailable or withdrawn IDs.
        raise PlanningError("source_not_available", 404)

    def review(self, actor_id, service, period, cutoff, fingerprint, note):
        actor = self._actor(actor_id)
        if not actor["can_review"]:
            raise PlanningError("review_not_allowed", 403)
        if not isinstance(note, str) or not note.strip() or len(note) > 300:
            raise PlanningError("review_note_required", 400)
        with self._lock:
            plan = self.plan(actor_id, service, period, cutoff)
            if plan["fingerprint"] != fingerprint:
                raise PlanningError("stale_plan", 409)
            if plan["plan_status"] != "ready_for_planning_review":
                raise PlanningError("plan_on_hold", 409)
            for prior in self.reviews.values():
                if prior["actor_id"] == actor_id and prior["fingerprint"] == fingerprint:
                    if prior["note"] == note:
                        return self._public_receipt(prior), False
                    raise PlanningError("review_content_changed", 409)
            receipt = {"receipt_id": secrets.token_hex(12), "actor_id": actor_id,
                       "site": actor["site"], "service": service, "period": period,
                       "cutoff": cutoff, "fingerprint": fingerprint, "note": note,
                       "action": "reviewed_planning_matrix",
                       "assessment_result": "unassessed",
                       "open_request_count": len(plan["requests"]),
                       "at": datetime.now(timezone.utc).isoformat()}
            self.reviews[receipt["receipt_id"]] = receipt
            return self._public_receipt(receipt), True

    @staticmethod
    def _public_receipt(receipt):
        return {k: receipt[k] for k in
                ("receipt_id", "actor_id", "site", "service", "period", "cutoff",
                 "fingerprint", "note", "action", "assessment_result",
                 "open_request_count", "at")}

    def history(self, actor_id, service, period, cutoff):
        plan = self.plan(actor_id, service, period, cutoff)
        # Exact current context only: a later receipt cannot reveal future sources.
        with self._lock:
            rows = [self._public_receipt(r) for r in self.reviews.values()
                    if r["actor_id"] == actor_id and r["fingerprint"] == plan["fingerprint"]]
        return sorted(rows, key=lambda r: r["at"], reverse=True)

    def export(self, actor_id, service, period, cutoff, receipt_id):
        actor = self._actor(actor_id)
        if not actor["can_review"]:
            raise PlanningError("export_not_allowed", 403)
        with self._lock:
            plan = self.plan(actor_id, service, period, cutoff)
            receipt = self.reviews.get(receipt_id)
            if not receipt or receipt["actor_id"] != actor_id:
                raise PlanningError("receipt_not_available", 404)
            if receipt["fingerprint"] != plan["fingerprint"]:
                raise PlanningError("stale_receipt", 409)
            return {"export_type": "reviewed_planning_matrix_json",
                    "not_audit_result": True, "not_oscal": True,
                    "receipt": self._public_receipt(receipt), "plan": plan}
