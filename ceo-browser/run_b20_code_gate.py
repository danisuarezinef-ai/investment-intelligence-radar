from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path

from build_b19_code_sandbox import build_sandbox
from programming_browser_loop import FreeWebCodingLoop, PatchSandbox, PowerShellChatGPTWebTransport


def local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def run_tests(root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc.returncode == 0, ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()


def git_output(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", default=str(local_root() / "CEO de IAs" / "browser-profile"))
    parser.add_argument("--evidence-dir", default=str(local_root() / "CEO de IAs" / "evidence"))
    parser.add_argument("--sandbox-root", default="")
    parser.add_argument("--port", type=int, default=9227)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sandbox_root = (
        Path(args.sandbox_root).expanduser().resolve()
        if args.sandbox_root
        else (local_root() / "CEO de IAs" / "sandboxes" / f"b20-{uuid.uuid4().hex[:10]}").resolve()
    )

    root = build_sandbox(sandbox_root)
    baseline_commit = git_output(root, "rev-parse", "HEAD")
    baseline_passed, baseline_output = run_tests(root)
    if baseline_passed:
        raise RuntimeError("B19 sandbox is invalid: intentional baseline bug did not fail")

    transport = PowerShellChatGPTWebTransport(
        driver_path=base / "windows_chatgpt_cdp_driver.ps1",
        recipe_path=base / "recipes" / "chatgpt_web.json",
        profile_dir=args.profile_dir,
        port=args.port,
        timeout_seconds=args.timeout,
    )
    loop = FreeWebCodingLoop(
        transport=transport,
        sandbox=PatchSandbox(root),
        max_turns=3,
    )
    result = loop.run(
        objective=(
            "Corrige únicamente el bug de calc.py para que add(a, b) devuelva la suma "
            "de ambos operandos. No cambies el test ni añadas comportamiento no relacionado."
        ),
        relevant_files=["calc.py", "test_calc.py"],
        test_command=[sys.executable, "-m", "unittest", "-q"],
        test_timeout_seconds=60,
    )

    final_passed, final_test_output = run_tests(root)
    current_commit = git_output(root, "rev-parse", "HEAD")
    commit_count = int(git_output(root, "rev-list", "--count", "HEAD"))
    remotes = git_output(root, "remote")
    final_source = (root / "calc.py").read_text(encoding="utf-8")
    diff = git_output(root, "diff", "--no-ext-diff", "--")

    evidence = {
        "schema_version": 1,
        "phase": "B19-B20",
        "ok": False,
        "status": result.status,
        "api_calls": 0,
        "paid_api_calls": 0,
        "sandbox_root": str(root),
        "baseline_commit": baseline_commit,
        "baseline_tests_failed_as_expected": not baseline_passed,
        "baseline_test_output": baseline_output[-4000:],
        "conversation_url": result.conversation_url,
        "attempts": [asdict(x) for x in result.attempts],
        "final_tests_passed": final_passed,
        "final_test_output": final_test_output[-4000:],
        "candidate_diff": diff,
        "source_verified": "return a + b" in final_source,
        "head_unchanged": current_commit == baseline_commit,
        "commit_count": commit_count,
        "remote_count": len([x for x in remotes.splitlines() if x.strip()]),
        "no_commit_push_merge": current_commit == baseline_commit and commit_count == 1 and not remotes.strip(),
        "failure_reason": result.failure_reason,
    }

    evidence["ok"] = bool(
        result.success
        and result.status == "CANDIDATE_VERIFIED"
        and final_passed
        and evidence["source_verified"]
        and evidence["no_commit_push_merge"]
        and diff.strip()
    )
    if evidence["ok"]:
        evidence["status"] = "B20_REAL_CHATGPT_CODE_GATE_PASS"

    evidence_path = evidence_dir / "B19_B20_CODE_GATE.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
