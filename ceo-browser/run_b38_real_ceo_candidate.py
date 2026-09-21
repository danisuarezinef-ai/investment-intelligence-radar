from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from programming_browser_loop import PowerShellChatGPTWebTransport
from real_code_candidate import BrowserFieldGuard, CandidateWorkspace, RealCodeCandidateRunner


TEST_FILE = r'''from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "ceo-browser"))

from simple_browser_task import SafeArtifactStore


class ReservedWindowsArtifactNames(unittest.TestCase):
    def test_normal_names_are_allowed(self):
        with tempfile.TemporaryDirectory() as td:
            store = SafeArtifactStore(td)
            p, _ = store.write("result.txt", "ok")
            self.assertTrue(p.is_file())
            p2, _ = store.write("nested/conman.txt", "ok")
            self.assertTrue(p2.is_file())

    def test_reserved_windows_device_names_are_rejected(self):
        blocked = [
            "CON",
            "con.txt",
            "PRN.log",
            "AUX",
            "NUL.md",
            "COM1",
            "com9.txt",
            "LPT1",
            "lpt9.dat",
            "nested/NUL.txt",
        ]
        with tempfile.TemporaryDirectory() as td:
            store = SafeArtifactStore(td)
            for name in blocked:
                with self.subTest(name=name):
                    with self.assertRaises(ValueError):
                        store.write(name, "blocked")


if __name__ == "__main__":
    unittest.main()
'''


def local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", default=str(local_root() / "CEO de IAs" / "browser-profile"))
    parser.add_argument("--evidence-dir", default=str(local_root() / "CEO de IAs" / "evidence"))
    parser.add_argument("--workspace-root", default="")
    parser.add_argument("--port", type=int, default=9227)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    field = BrowserFieldGuard(evidence_dir).require_verified()

    repo_root = Path(__file__).resolve().parents[1]
    candidate_id = f"B38-{uuid.uuid4().hex[:10]}"
    workspace_root = (
        Path(args.workspace_root).expanduser().resolve()
        if args.workspace_root
        else (local_root() / "CEO de IAs" / "candidates" / candidate_id).resolve()
    )

    workspace = CandidateWorkspace.create(
        source_root=repo_root,
        workspace_root=workspace_root,
        files=[
            "ceo-browser/simple_browser_task.py",
            "ceo-browser/browser_ai_worker.py",
        ],
        extra_files={"test_b38_candidate.py": TEST_FILE},
    )

    base = Path(__file__).resolve().parent
    transport = PowerShellChatGPTWebTransport(
        driver_path=base / "windows_chatgpt_cdp_driver.ps1",
        recipe_path=base / "recipes" / "chatgpt_web.json",
        profile_dir=args.profile_dir,
        port=args.port,
        timeout_seconds=args.timeout,
    )

    runner = RealCodeCandidateRunner(
        transport=transport,
        source_root=repo_root,
        evidence_dir=evidence_dir,
    )
    result = runner.run(
        workspace=workspace,
        objective=(
            "Endurece SafeArtifactStore._resolve_name en ceo-browser/simple_browser_task.py. "
            "Debe rechazar los nombres de dispositivo reservados por Windows CON, PRN, AUX, NUL, "
            "COM1-COM9 y LPT1-LPT9, sin distinguir mayúsculas/minúsculas y también cuando llevan "
            "una extensión, en cualquier segmento de la ruta. Mantén permitidos nombres normales "
            "como conman.txt. Modifica únicamente ceo-browser/simple_browser_task.py y realiza el "
            "cambio mínimo necesario para superar el test proporcionado."
        ),
        relevant_files=[
            "ceo-browser/simple_browser_task.py",
            "ceo-browser/browser_ai_worker.py",
            "test_b38_candidate.py",
        ],
        allowed_edit_paths=["ceo-browser/simple_browser_task.py"],
        test_command=[sys.executable, "-m", "unittest", "-q", "test_b38_candidate.py"],
        candidate_id=candidate_id,
    )

    summary = {
        "schema_version": 1,
        "phase": "B38",
        "ok": bool(result.success),
        "status": "B38_REAL_CEO_CANDIDATE_PASS" if result.success else result.status,
        "candidate_id": candidate_id,
        "candidate_status": result.status,
        "candidate_evidence": str(evidence_dir / f"{candidate_id}.json"),
        "candidate_patch": result.diff_path,
        "candidate_patch_sha256": result.diff_sha256,
        "workspace_root": result.workspace_root,
        "conversation_url": result.conversation_url,
        "tests_passed": result.tests_passed,
        "original_source_unchanged": result.original_source_unchanged,
        "commit_count": result.commit_count,
        "remote_count": len(result.remotes),
        "api_calls": result.api_calls,
        "paid_api_calls": result.paid_api_calls,
        "browser_field_verified": field.get("BROWSER_FIELD_VERIFIED") is True,
        "automatic_merge": False,
        "production_promotion": False,
        "human_review_required": True,
        "failure_reason": result.failure_reason,
    }
    summary_path = evidence_dir / "B38_REAL_CEO_CANDIDATE.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
