"""Native loopback API boundary checks; no external service or model."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import urlencode

from audit_desk.core import Desk
from audit_desk.server import make_server

EARLY = "2026-09-10T09:00:00Z"
LATE = "2026-09-12T09:00:00Z"


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = make_server(port=0, desk=Desk())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_port)
        self.ctx = {"service": "MES-REPORT-A", "period": "2026-08", "cutoff": EARLY}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def call(self, path, actor="planner_a", data=None):
        headers = {"X-Demo-Actor": actor}
        if data is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(data, ensure_ascii=False).encode()
        request = urllib.request.Request(self.base + path, headers=headers, data=data)
        try:
            with urllib.request.urlopen(request, timeout=3) as result:
                return result.status, json.load(result), result.headers
        except urllib.error.HTTPError as error:
            return error.code, json.load(error), error.headers

    def path(self, name, ctx=None):
        return name + "?" + urlencode(ctx or self.ctx)

    def test_projected_plan_source_and_generic_denial(self):
        code, plan, headers = self.call(self.path("/api/plan"))
        self.assertEqual(code, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("PLANT-B", json.dumps(plan))
        self.assertNotIn("EV-INVENTORY-AUG-R2", json.dumps(plan))
        code, body, _ = self.call(self.path("/api/source/EV-INVENTORY-AUG-R2"))
        self.assertEqual((code, body["error"]), (404, "source_not_available"))
        code, body, _ = self.call(self.path("/api/source/EV-ACCESS-B-AUG-R1"))
        self.assertEqual((code, body["error"]), (404, "source_not_available"))
        code, body, _ = self.call(self.path("/api/plan", dict(self.ctx, service="MES-REPORT-B")))
        self.assertEqual((code, body["error"]), (403, "scope_not_available"))

    def test_review_history_and_export_recheck_context(self):
        _, early, _ = self.call(self.path("/api/plan"))
        body = dict(self.ctx, fingerprint=early["fingerprint"], note="조기 자료로 계획만 검토")
        code, receipt, _ = self.call("/api/reviews", data=body)
        self.assertEqual(code, 201)
        code, exported, _ = self.call(self.path("/api/export/" + receipt["receipt_id"]))
        self.assertEqual(code, 200)
        self.assertTrue(exported["not_audit_result"])
        late_ctx = dict(self.ctx, cutoff=LATE)
        _, later, _ = self.call(self.path("/api/plan", late_ctx))
        code, later_receipt, _ = self.call("/api/reviews",
            data=dict(late_ctx, fingerprint=later["fingerprint"],
                      note="EV-INVENTORY-AUG-R2 이후 계획 검토"))
        self.assertEqual(code, 201)
        code, old_history, _ = self.call(self.path("/api/reviews"))
        self.assertEqual(code, 200)
        self.assertEqual([x["receipt_id"] for x in old_history], [receipt["receipt_id"]])
        self.assertNotIn("EV-INVENTORY-AUG-R2", json.dumps(old_history))
        code, error, _ = self.call(self.path("/api/export/" + receipt["receipt_id"], late_ctx))
        self.assertEqual((code, error["error"]), (409, "stale_receipt"))
        code, error, _ = self.call(self.path("/api/export/" + later_receipt["receipt_id"]))
        self.assertEqual((code, error["error"]), (409, "stale_receipt"))

    def test_viewer_and_body_shape(self):
        _, plan, _ = self.call(self.path("/api/plan"), actor="viewer_a")
        code, error, _ = self.call("/api/reviews", actor="viewer_a",
            data=dict(self.ctx, fingerprint=plan["fingerprint"], note="cannot review"))
        self.assertEqual((code, error["error"]), (403, "review_not_allowed"))
        code, error, _ = self.call("/api/reviews", data=dict(self.ctx, fingerprint="stale", note="x"))
        self.assertEqual((code, error["error"]), (409, "stale_plan"))
        code, error, _ = self.call("/api/reviews", data={"unexpected": "field"})
        self.assertEqual((code, error["error"]), (400, "review_body_shape"))

    def test_static_allowlist_and_loopback_only(self):
        code, _, _ = self.call("/api/not-here")
        self.assertEqual(code, 404)
        with self.assertRaisesRegex(ValueError, "loopback_only"):
            make_server(host="0.0.0.0", port=0)


if __name__ == "__main__":
    unittest.main()
