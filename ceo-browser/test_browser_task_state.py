from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from browser_task_state import (
    BrowserTaskLedger,
    BrowserTaskRecord,
    BoundedRecoveryPolicy,
    classify_browser_failure,
    verify_artifact_integrity,
)
from durable_browser_task import DurableArtifactRunner
from simple_browser_task import SafeArtifactStore
from build_b19_code_sandbox import build_sandbox
from sandbox_recovery import SandboxRecovery


class SequenceBrowser:
    def __init__(self, rows):
        self.rows=list(rows)
        self.calls=0
    def ask(self,prompt,*,conversation_url=None):
        self.calls+=1
        row=self.rows.pop(0)
        if isinstance(row,Exception):
            raise row
        return row


class DurableStateTests(unittest.TestCase):
    def test_ledger_roundtrip_and_integrity(self):
        with tempfile.TemporaryDirectory() as td:
            ledger=BrowserTaskLedger(Path(td)/"ledger")
            artifact=Path(td)/"a.txt"
            artifact.write_text("abc",encoding="utf-8")
            import hashlib
            r=BrowserTaskRecord(
                task_id="t1",idempotency_key="k1",objective_sha256="o",
                status="COMPLETED",artifact_path=str(artifact),
                artifact_sha256=hashlib.sha256(artifact.read_bytes()).hexdigest(),
                artifact_chars=3,
            )
            ledger.save(r)
            loaded=ledger.load("t1")
            self.assertEqual(loaded.status,"COMPLETED")
            self.assertTrue(verify_artifact_integrity(loaded)[0])

    def test_completed_idempotency_reuses_without_browser_call(self):
        with tempfile.TemporaryDirectory() as td:
            store=SafeArtifactStore(Path(td)/"artifacts")
            ledger=BrowserTaskLedger(Path(td)/"ledger")
            browser=SequenceBrowser([{
                "response":"<CEO_ARTIFACT>ok</CEO_ARTIFACT><CEO_DONE>true</CEO_DONE>",
                "conversation_url":"https://chatgpt.test/c/1",
            }])
            runner=DurableArtifactRunner(transport=browser,store=store,ledger=ledger)
            first=runner.run(task_id="t1",idempotency_key="same",objective="make",acceptance=[],artifact_name="a.txt")
            second=runner.run(task_id="t2",idempotency_key="same",objective="make",acceptance=[],artifact_name="a.txt")
            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertTrue(second.reused)
            self.assertEqual(browser.calls,1)

    def test_safe_pre_send_failure_retries_once(self):
        with tempfile.TemporaryDirectory() as td:
            browser=SequenceBrowser([
                RuntimeError("PROMPT_NOT_SUBMITTED: no submit evidence"),
                {"response":"<CEO_ARTIFACT>ok</CEO_ARTIFACT><CEO_DONE>true</CEO_DONE>","conversation_url":"https://chatgpt.test/c/2"},
            ])
            runner=DurableArtifactRunner(
                transport=browser,
                store=SafeArtifactStore(Path(td)/"artifacts"),
                ledger=BrowserTaskLedger(Path(td)/"ledger"),
            )
            result=runner.run(task_id="t1",idempotency_key="k",objective="make",acceptance=[],artifact_name="a.txt")
            self.assertTrue(result.success,result)
            self.assertEqual(browser.calls,2)

    def test_ambiguous_response_timeout_does_not_repeat(self):
        with tempfile.TemporaryDirectory() as td:
            browser=SequenceBrowser([RuntimeError("RESPONSE_TIMEOUT: prompt may have been submitted")])
            ledger=BrowserTaskLedger(Path(td)/"ledger")
            runner=DurableArtifactRunner(
                transport=browser,
                store=SafeArtifactStore(Path(td)/"artifacts"),
                ledger=ledger,
            )
            result=runner.run(task_id="t1",idempotency_key="k",objective="make",acceptance=[],artifact_name="a.txt")
            self.assertFalse(result.success)
            self.assertEqual(result.status,"WAITING_REVIEW")
            self.assertEqual(browser.calls,1)
            self.assertEqual(ledger.load("t1").status,"WAITING_REVIEW")

    def test_login_never_auto_retries(self):
        p=BoundedRecoveryPolicy()
        self.assertEqual(p.decision(attempts=1,status="LOGIN_REQUIRED"),"WAIT_HUMAN")
        self.assertEqual(classify_browser_failure("LOGIN_REQUIRED"),"HUMAN_ACTION")

    def test_sandbox_restore_is_marker_and_remote_guarded(self):
        with tempfile.TemporaryDirectory() as td:
            root=build_sandbox(Path(td)/"repo")
            guard=SandboxRecovery(root)
            (root/"calc.py").write_text("broken\n",encoding="utf-8")
            (root/"junk.tmp").write_text("junk",encoding="utf-8")
            guard.restore_baseline()
            self.assertIn("return a - b",(root/"calc.py").read_text(encoding="utf-8"))
            self.assertFalse((root/"junk.tmp").exists())


if __name__=="__main__":
    unittest.main()
