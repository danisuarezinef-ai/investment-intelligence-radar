from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from browser_ai_worker import BrowserResultProtocol
from real_code_candidate import (
    BrowserFieldGuard,
    CandidateDiffPolicy,
    CandidatePolicy,
    CandidateWorkspace,
    RealCodeCandidateRunner,
)


class CandidateWorkflowTests(unittest.TestCase):
    def test_field_guard_requires_verified_state(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            guard=BrowserFieldGuard(root)
            with self.assertRaises(RuntimeError):
                guard.require_verified()
            (root/"BROWSER_FIELD_STATE.json").write_text(json.dumps({
                "BROWSER_FIELD_VERIFIED": True,
                "api_calls_required": 0,
                "production_promotion_allowed": False,
                "automatic_merge_allowed": False,
            }),encoding="utf-8")
            row=guard.require_verified()
            self.assertTrue(row["BROWSER_FIELD_VERIFIED"])

    def test_candidate_workspace_does_not_touch_source_and_has_no_remote(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            src=base/"src"; src.mkdir()
            (src/"a.py").write_text("VALUE=1\n",encoding="utf-8")
            source_hash=hashlib.sha256((src/"a.py").read_bytes()).hexdigest()
            ws=CandidateWorkspace.create(
                source_root=src,
                workspace_root=base/"candidate",
                files=["a.py"],
                extra_files={"test_candidate.py":"# test\n"},
            )
            (ws.root/"a.py").write_text("VALUE=2\n",encoding="utf-8")
            self.assertEqual(hashlib.sha256((src/"a.py").read_bytes()).hexdigest(),source_hash)
            self.assertEqual(ws.commit_count(),1)
            self.assertEqual(ws.remotes(),[])

    def test_diff_policy_allows_only_declared_small_text_change(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            src=base/"src"; src.mkdir()
            (src/"a.py").write_text("VALUE=1\n",encoding="utf-8")
            (src/"b.py").write_text("VALUE=1\n",encoding="utf-8")
            ws=CandidateWorkspace.create(
                source_root=src,
                workspace_root=base/"candidate",
                files=["a.py","b.py"],
            )
            (ws.root/"a.py").write_text("VALUE=2\n",encoding="utf-8")
            ok,detail=CandidateDiffPolicy(CandidatePolicy(("a.py",))).inspect(workspace=ws)
            self.assertTrue(ok,detail)
            (ws.root/"b.py").write_text("VALUE=2\n",encoding="utf-8")
            ok,detail=CandidateDiffPolicy(CandidatePolicy(("a.py",))).inspect(workspace=ws)
            self.assertFalse(ok)
            self.assertIn("b.py",detail["bad_paths"])


    def test_real_candidate_runner_keeps_source_untouched_and_emits_review_candidate(self):
        class FakeBrowser:
            def ask(self, prompt, *, conversation_url=None):
                return {
                    "ok": True,
                    "conversation_url": conversation_url or "https://chatgpt.test/c/candidate",
                    "response": (
                        "<CEO_PATCH>diff --git a/a.py b/a.py\n"
                        "--- a/a.py\n"
                        "+++ b/a.py\n"
                        "@@ -1,2 +1,2 @@\n"
                        " def add(a, b):\n"
                        "-    return a - b\n"
                        "+    return a + b\n"
                        "</CEO_PATCH>\n"
                        "<CEO_DONE>true</CEO_DONE>"
                    ),
                }

        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            src=base/"src"; src.mkdir()
            (src/"a.py").write_text("def add(a, b):\n    return a - b\n",encoding="utf-8")
            (src/"test_candidate.py").write_text(
                "import unittest\nfrom a import add\n"
                "class T(unittest.TestCase):\n"
                "    def test_add(self): self.assertEqual(add(2,3),5)\n",
                encoding="utf-8",
            )
            original_hash=hashlib.sha256((src/"a.py").read_bytes()).hexdigest()
            ws=CandidateWorkspace.create(
                source_root=src,
                workspace_root=base/"candidate",
                files=["a.py","test_candidate.py"],
            )
            runner=RealCodeCandidateRunner(
                transport=FakeBrowser(),
                source_root=src,
                evidence_dir=base/"evidence",
            )
            result=runner.run(
                workspace=ws,
                objective="Fix add.",
                relevant_files=["a.py","test_candidate.py"],
                allowed_edit_paths=["a.py"],
                test_command=[__import__("sys").executable,"-m","unittest","-q","test_candidate.py"],
                candidate_id="candidate-test",
            )
            self.assertTrue(result.success,result)
            self.assertEqual(result.status,"CANDIDATE_READY_FOR_HUMAN_REVIEW")
            self.assertEqual(result.commit_count,1)
            self.assertEqual(result.remotes,[])
            self.assertTrue(result.original_source_unchanged)
            self.assertTrue(result.tests_passed)
            self.assertEqual(hashlib.sha256((src/"a.py").read_bytes()).hexdigest(),original_hash)
            self.assertTrue(Path(result.diff_path).is_file())
            self.assertTrue((base/"evidence"/"candidate-test.json").is_file())

    def test_forbidden_sensitive_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td)
            src=base/"src"; src.mkdir()
            (src/"secret.key").write_text("x\n",encoding="utf-8")
            ws=CandidateWorkspace.create(
                source_root=src,
                workspace_root=base/"candidate",
                files=["secret.key"],
            )
            (ws.root/"secret.key").write_text("y\n",encoding="utf-8")
            ok,detail=CandidateDiffPolicy(CandidatePolicy(("secret.key",))).inspect(workspace=ws)
            self.assertFalse(ok)
            self.assertIn("secret.key",detail["forbidden_paths"])


if __name__=="__main__":
    unittest.main()
