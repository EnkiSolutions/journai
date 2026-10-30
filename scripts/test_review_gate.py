import copy
import unittest
from review_gate import GateError, certificate_parts, evaluate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "pr": {"state": "open", "draft": False, "head": {"sha": "abc"}},
            "reviews": [{"id": 1, "user": {"login": "coderabbitai[bot]", "type": "Bot"}, "state": "APPROVED", "commit_id": "abc"}],
            "checks": [{"id": 1, "name": "CodeRabbit", "status": "completed", "conclusion": "success", "app": {"id": 1, "slug": "coderabbitai"}}],
            "statuses": [], "threads": [],
            "files": [{"filename": "app.py", "additions": 1, "deletions": 1,
                       "patch": "@@ -1 +1 @@\n-old\n+new"}],
        }
        self.certificate = {"head_sha": "abc", "decision": "approve", "summary": "F01", "validation": ["test passed"], "lines": [
            {"path": "app.py", "side": side, "line": 1, "reason": "F01 : raison spécifique justifiant cette modification"}
            for side in ("LEFT", "RIGHT")]}

    def test_complete_certificate(self):
        self.assertEqual(evaluate(self.snapshot, self.certificate), "abc")

    def test_missing_or_stale_bot_review(self):
        for change in ([], [{**self.snapshot["reviews"][0], "commit_id": "old"}]):
            with self.subTest(change=change), self.assertRaises(GateError):
                evaluate({**self.snapshot, "reviews": change})

    def test_open_bot_thread(self):
        self.snapshot["threads"] = [{"isResolved": False, "comments": {"nodes": [{"author": {"login": "coderabbitai"}}]}}]
        with self.assertRaises(GateError):
            evaluate(self.snapshot)

    def test_latest_request_changes_blocks(self):
        self.snapshot["reviews"].append({**self.snapshot["reviews"][0], "id": 2, "state": "CHANGES_REQUESTED"})
        with self.assertRaises(GateError):
            evaluate(self.snapshot)

    def test_success_status_alone_is_insufficient(self):
        self.snapshot["checks"] = []
        self.snapshot["statuses"] = [{"context": "CodeRabbit", "state": "success"}]
        with self.assertRaises(GateError):
            evaluate(self.snapshot)

    def test_incomplete_duplicate_or_stale_certificate(self):
        for mutation in ("missing", "duplicate", "stale"):
            cert = copy.deepcopy(self.certificate)
            if mutation == "missing": cert["lines"].pop()
            elif mutation == "duplicate": cert["lines"].append(cert["lines"][0])
            else: cert["head_sha"] = "old"
            with self.subTest(mutation=mutation), self.assertRaises(GateError):
                evaluate(self.snapshot, cert)

    def test_truncated_patch_is_rejected(self):
        self.snapshot["files"][0]["additions"] = 2
        with self.assertRaises(GateError):
            evaluate(self.snapshot, self.certificate)

    def test_pending_other_check_blocks(self):
        self.snapshot["checks"].append({"id": 2, "name": "CI", "status": "in_progress", "conclusion": None})
        with self.assertRaises(GateError):
            evaluate(self.snapshot)

    def test_large_certificate_keeps_every_line(self):
        lines = [{"line": i, "reason": "F01 : vérifier la cohérence de cette ligne"} for i in range(100)]
        parts = certificate_parts({"lines": lines}, budget=200)
        self.assertGreater(len(parts), 1)
        self.assertEqual([line for part in parts for line in part], lines)

    def test_oversized_single_reason_is_rejected(self):
        with self.assertRaises(GateError):
            certificate_parts({"lines": [{"reason": "x" * 1000}]}, budget=100)


if __name__ == "__main__":
    unittest.main()
