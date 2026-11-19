import copy
import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, mock_open, patch

from review_gate import GateError, certificate_parts, evaluate, index_body, main


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

    def publish(self, certificate, snapshots=None, url="https://github.com/example#issuecomment-1"):
        github = Mock()
        github.snapshot.side_effect = snapshots or [self.snapshot, self.snapshot]
        github.request.side_effect = [{"html_url": url}, {"html_url": "https://github.com/index"}, {}]
        with patch("review_gate.GitHub", return_value=github), \
             patch("builtins.open", mock_open(read_data=json.dumps(certificate))), \
             patch("sys.argv", ["review_gate.py", "--pr", "26", "--certificate", "cert.json", "--publish"]), \
             redirect_stdout(io.StringIO()):
            try:
                main()
            except GateError as error:
                return github, error
        return github, None

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

    def test_large_validation_index_rejected_before_posts(self):
        cert = copy.deepcopy(self.certificate)
        cert["validation"] = [{"test": "api", "ok": True} for _ in range(1500)]
        compact = {key: value for key, value in cert.items() if key != "lines"}
        compact.update(line_count=2, line_justification_comments=[])
        self.assertLessEqual(len(json.dumps(compact, ensure_ascii=False).encode("utf8")), 45000)
        github, error = self.publish(cert)
        self.assertIsInstance(error, GateError)
        github.request.assert_not_called()

    def test_index_utf8_and_url_reserve_boundary(self):
        cert = copy.deepcopy(self.certificate)
        cert["summary"] = "é"
        index = {key: value for key, value in cert.items() if key != "lines"}
        index.update(line_count=2, line_justification_comments=["x" * 2046])
        cert["summary"] += "x" * (45000 - len(index_body(index).encode("utf8")))
        url = "https://example.test/" + 'é"' * 300
        github, error = self.publish(cert, url=url)
        self.assertIsNone(error)
        self.assertEqual(github.request.call_count, 3)
        index_post = github.request.call_args_list[1].args
        self.assertIn(json.dumps(url, ensure_ascii=False), index_post[2]["body"])
        self.assertIn("/statuses/abc", github.request.call_args_list[2].args[0])
        cert["summary"] += "é"
        github, error = self.publish(cert)
        self.assertIsInstance(error, GateError)
        github.request.assert_not_called()

    def test_reserve_counts_every_part_before_posts(self):
        cert = copy.deepcopy(self.certificate)
        for line in cert["lines"]:
            line["reason"] = "F01 justification " + "x" * 26000
        self.assertEqual(len(certificate_parts(cert)), 2)
        index = {key: value for key, value in cert.items() if key != "lines"}
        index.update(line_count=2, line_justification_comments=["x" * 2046] * 2)
        cert["summary"] += "x" * (45001 - len(index_body(index).encode("utf8")))
        github, error = self.publish(cert)
        self.assertIsInstance(error, GateError)
        github.request.assert_not_called()

    def test_oversized_returned_url_never_publishes_index_or_status(self):
        github, error = self.publish(self.certificate, url="é" * 1024)
        self.assertIsInstance(error, GateError)
        self.assertEqual(github.request.call_count, 1)

    def test_invalid_certificates_and_coderabbit_never_post(self):
        for mutation in ("coverage", "sha", "coderabbit"):
            cert = copy.deepcopy(self.certificate)
            snapshot = copy.deepcopy(self.snapshot)
            if mutation == "coverage": cert["lines"].pop()
            elif mutation == "sha": cert["head_sha"] = "old"
            else: snapshot["reviews"] = []
            with self.subTest(mutation=mutation):
                github, error = self.publish(cert, [snapshot])
                self.assertIsInstance(error, GateError)
                github.request.assert_not_called()

    def test_sha_change_before_index_never_publishes_reviewer_status(self):
        stale = copy.deepcopy(self.snapshot)
        stale["pr"]["head"]["sha"] = "new"
        github, error = self.publish(self.certificate, [self.snapshot, stale])
        self.assertIsInstance(error, GateError)
        self.assertEqual(github.request.call_count, 1)

    def test_oversized_single_reason_is_rejected(self):
        with self.assertRaises(GateError):
            certificate_parts({"lines": [{"reason": "x" * 1000}]}, budget=100)


if __name__ == "__main__":
    unittest.main()
