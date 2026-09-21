from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from build_b19_code_sandbox import build_sandbox
from browser_provider_pool import BrowserProviderRegistry
from finalize_browser_field import finalize_field
from first_trial_safety import atomic_json, bounded_text
from programming_browser_loop import FreeWebCodingLoop, PatchSandbox, PowerShellWebAITransport
from simple_browser_task import BrowserArtifactTaskRunner, SafeArtifactStore


def local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def normalize_url(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        u = urlsplit(raw)
        path = u.path.rstrip("/")
        return urlunsplit((u.scheme.lower(), u.netloc.lower(), path, "", ""))
    except Exception:
        return raw.rstrip("/")


def run_tests(root: Path) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    return proc.returncode == 0, output[-12000:]


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


def prepare_session(
    *,
    base: Path,
    profile_dir: Path,
    recipe_path: Path,
    port: int,
    timeout: int,
    evidence_dir: Path,
) -> tuple[bool, str]:
    helper = base / "open_web_ai_profile.ps1"
    driver = base / "windows_chatgpt_cdp_driver.ps1"
    powershell = "powershell.exe" if os.name == "nt" else "pwsh"
    cmd = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(helper),
        "-ProfileDir",
        str(profile_dir),
        "-Port",
        str(port),
        "-TimeoutSeconds",
        str(max(300, timeout)),
        "-RecipePath",
        str(recipe_path),
        "-DriverPath",
        str(driver),
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=max(360, timeout + 120),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = bounded_text(((proc.stdout or "") + "\n" + (proc.stderr or "")).strip(), 128 * 1024)
    (evidence_dir / "SESSION_PREP.log").write_text(output, encoding="utf-8")
    return proc.returncode == 0, output


def phase_b14(
    *,
    transport: PowerShellWebAITransport,
    evidence_dir: Path,
    provider: str,
    trial_id: str,
) -> tuple[bool, str]:
    path = evidence_dir / "B09_B14_PHYSICAL_GATE.json"
    evidence = {
        "schema_version": 2,
        "phase": "B09-B14",
        "trial_id": trial_id,
        "ok": False,
        "status": "B14_NOT_RUN",
        "provider": provider,
        "api_calls": 0,
        "paid_api_calls": 0,
        "same_conversation": False,
        "conversation_url": "",
        "turn_1": {},
        "turn_2": {},
        "failure_reason": "",
    }
    try:
        token1 = "CEO_BROWSER_TURN_1_OK"
        token2 = "CEO_BROWSER_TURN_2_OK"
        t1 = transport.ask(f"Responde únicamente con el texto {token1}")
        if token1 not in str(t1.get("response") or ""):
            raise RuntimeError("B14 turno 1 no devolvió el token esperado")
        if not bool(t1.get("submission_verified")):
            raise RuntimeError("B14 turno 1 no tiene evidencia B10 de envío")
        if not bool(t1.get("generation_started")):
            raise RuntimeError("B14 turno 1 no tiene evidencia B11 de generación")
        if not bool(t1.get("conversation_stable")):
            raise RuntimeError("B14 turno 1 no tiene evidencia B13 de conversación estable")

        conversation = str(t1.get("conversation_url") or "").strip()
        if not conversation:
            raise RuntimeError("B13 turno 1 no devolvió URL de conversación")

        t2 = transport.ask(
            f"Sin cambiar de conversación, responde únicamente con el texto {token2}",
            conversation_url=conversation,
        )
        if token2 not in str(t2.get("response") or ""):
            raise RuntimeError("B14 turno 2 no devolvió el token esperado")
        if not bool(t2.get("submission_verified")):
            raise RuntimeError("B14 turno 2 no tiene evidencia B10 de envío")
        if not bool(t2.get("generation_started")):
            raise RuntimeError("B14 turno 2 no tiene evidencia B11 de generación")
        if not bool(t2.get("conversation_stable")):
            raise RuntimeError("B14 turno 2 no tiene evidencia B13 de conversación estable")

        conversation2 = str(t2.get("conversation_url") or "").strip()
        same = normalize_url(conversation2) == normalize_url(conversation)
        if not same:
            raise RuntimeError(
                f"B14 conversation drift: {normalize_url(conversation)!r} -> {normalize_url(conversation2)!r}"
            )

        evidence.update(
            {
                "ok": True,
                "status": "B14_REAL_WEB_TWO_TURN_PASS",
                "same_conversation": True,
                "conversation_url": conversation2,
                "turn_1": {
                    "response": str(t1.get("response") or ""),
                    "response_chars": int(t1.get("response_chars") or 0),
                    "typed_chars": int(t1.get("typed_chars") or 0),
                    "send_method": str(t1.get("send_method") or ""),
                    "completion_reason": str(t1.get("completion_reason") or ""),
                },
                "turn_2": {
                    "response": str(t2.get("response") or ""),
                    "response_chars": int(t2.get("response_chars") or 0),
                    "typed_chars": int(t2.get("typed_chars") or 0),
                    "send_method": str(t2.get("send_method") or ""),
                    "completion_reason": str(t2.get("completion_reason") or ""),
                },
            }
        )
    except Exception as exc:
        evidence["status"] = "B14_REAL_WEB_TWO_TURN_FAIL"
        evidence["failure_reason"] = bounded_text(f"{type(exc).__name__}: {exc}", 16000)
    atomic_json(path, evidence)
    return bool(evidence["ok"]), str(evidence["failure_reason"] or evidence["status"])


def phase_b18(
    *,
    transport: PowerShellWebAITransport,
    evidence_dir: Path,
    provider: str,
    trial_id: str,
) -> tuple[bool, str]:
    expected = f"CEO_BROWSER_ARTIFACT_OK\nPROVIDER={provider}\nAPIS=0"
    runner = BrowserArtifactTaskRunner(
        transport=transport,
        artifact_store=SafeArtifactStore(evidence_dir),
    )
    result = runner.run(
        objective=(
            "Crea un artefacto de validación de exactamente tres líneas. "
            f"La primera debe ser CEO_BROWSER_ARTIFACT_OK, la segunda PROVIDER={provider} "
            "y la tercera APIS=0. No añadas ninguna otra línea dentro del artefacto."
        ),
        acceptance=[
            "Exactly three lines inside CEO_ARTIFACT.",
            "Line 1 is CEO_BROWSER_ARTIFACT_OK.",
            f"Line 2 is PROVIDER={provider}.",
            "Line 3 is APIS=0.",
            "Finish with <CEO_DONE>true</CEO_DONE>.",
        ],
        artifact_name="B18_PRIMER_ARTEFACTO.txt",
    )
    evidence = {
        "schema_version": 2,
        "phase": "B15-B18",
        "trial_id": trial_id,
        "provider": provider,
        "ok": bool(result.success),
        "status": result.status,
        "api_calls": 0,
        "paid_api_calls": 0,
        "artifact_path": result.artifact_path,
        "artifact_sha256": result.artifact_sha256,
        "artifact_chars": result.artifact_chars,
        "conversation_url": result.conversation_url,
        "metadata": result.metadata,
        "failure_reason": result.failure_reason,
        "content_verified": False,
    }
    if result.success:
        actual = Path(result.artifact_path).read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        if actual != expected:
            evidence["ok"] = False
            evidence["status"] = "ARTIFACT_CONTENT_MISMATCH"
            evidence["failure_reason"] = f"unexpected artifact content: {actual!r}"
            Path(result.artifact_path).unlink(missing_ok=True)
        else:
            evidence["content_verified"] = True
            evidence["status"] = "B18_REAL_BROWSER_ARTIFACT_PASS"
    atomic_json(evidence_dir / "B15_B18_PHYSICAL_GATE.json", evidence)
    return bool(evidence["ok"]), str(evidence["failure_reason"] or evidence["status"])


def phase_b20(
    *,
    transport: PowerShellWebAITransport,
    evidence_dir: Path,
    provider: str,
    trial_id: str,
) -> tuple[bool, str]:
    sandbox_root = (
        local_root()
        / "CEO de IAs"
        / "sandboxes"
        / f"{trial_id.lower()}-b20-{uuid.uuid4().hex[:6]}"
    ).resolve()
    evidence = {
        "schema_version": 2,
        "phase": "B19-B20",
        "trial_id": trial_id,
        "provider": provider,
        "ok": False,
        "status": "B20_NOT_RUN",
        "api_calls": 0,
        "paid_api_calls": 0,
        "sandbox_root": str(sandbox_root),
        "baseline_commit": "",
        "baseline_tests_failed_as_expected": False,
        "baseline_test_output": "",
        "conversation_url": "",
        "attempts": [],
        "final_tests_passed": False,
        "final_test_output": "",
        "candidate_diff": "",
        "source_verified": False,
        "head_unchanged": False,
        "commit_count": 0,
        "remote_count": 0,
        "no_commit_push_merge": False,
        "failure_reason": "",
    }
    try:
        root = build_sandbox(sandbox_root)
        baseline_commit = git_output(root, "rev-parse", "HEAD")
        baseline_passed, baseline_output = run_tests(root)
        evidence["baseline_commit"] = baseline_commit
        evidence["baseline_tests_failed_as_expected"] = not baseline_passed
        evidence["baseline_test_output"] = baseline_output[-4000:]
        if baseline_passed:
            raise RuntimeError("B19 sandbox is invalid: intentional baseline bug did not fail")

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

        evidence.update(
            {
                "status": result.status,
                "conversation_url": result.conversation_url,
                "attempts": [asdict(x) for x in result.attempts],
                "final_tests_passed": final_passed,
                "final_test_output": final_test_output[-4000:],
                "candidate_diff": diff,
                "source_verified": "return a + b" in final_source,
                "head_unchanged": current_commit == baseline_commit,
                "commit_count": commit_count,
                "remote_count": len([x for x in remotes.splitlines() if x.strip()]),
                "no_commit_push_merge": (
                    current_commit == baseline_commit and commit_count == 1 and not remotes.strip()
                ),
                "failure_reason": result.failure_reason,
            }
        )
        evidence["ok"] = bool(
            result.success
            and result.status == "CANDIDATE_VERIFIED"
            and final_passed
            and evidence["source_verified"]
            and evidence["no_commit_push_merge"]
            and diff.strip()
        )
        if evidence["ok"]:
            evidence["status"] = "B20_REAL_WEB_CODE_GATE_PASS"
    except Exception as exc:
        evidence["status"] = "B20_REAL_WEB_CODE_GATE_FAIL"
        evidence["failure_reason"] = bounded_text(f"{type(exc).__name__}: {exc}", 16000)

    atomic_json(evidence_dir / "B19_B20_CODE_GATE.json", evidence)
    return bool(evidence["ok"]), str(evidence["failure_reason"] or evidence["status"])


def main() -> int:
    parser = argparse.ArgumentParser()
    base = Path(__file__).resolve().parent
    local = local_root()
    parser.add_argument("--provider", default="chatgpt-web")
    parser.add_argument("--profile-dir", default="")
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--canonical-out", required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--port", type=int, default=9227)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    registry = BrowserProviderRegistry(base_dir=base, base_port=args.port)
    spec = registry.resolve(args.provider)
    profile_dir = (
        Path(args.profile_dir).expanduser().resolve()
        if args.profile_dir
        else spec.profile_dir
    )
    recipe_path = spec.recipe_path
    provider = spec.name
    effective_port = spec.port

    summary = {
        "schema_version": 2,
        "trial_id": args.trial_id,
        "provider": provider,
        "evidence_dir": str(evidence_dir),
        "profile_dir": str(profile_dir),
        "port": effective_port,
        "api_calls": 0,
        "paid_api_calls": 0,
        "session_prepared": False,
        "phases": {},
        "ok": False,
        "status": "STARTED",
        "failure_reason": "",
    }

    session_ok, session_detail = prepare_session(
        base=base,
        profile_dir=profile_dir,
        recipe_path=recipe_path,
        port=effective_port,
        timeout=args.timeout,
        evidence_dir=evidence_dir,
    )
    summary["session_prepared"] = session_ok
    if not session_ok:
        summary["status"] = "SESSION_PREP_FAILED"
        summary["failure_reason"] = session_detail[-12000:]
        atomic_json(evidence_dir / "FIELD_CAMPAIGN_RESULT.json", summary)
        state = finalize_field(
            evidence_dir,
            trial_id=args.trial_id,
            provider=provider,
            canonical_out=args.canonical_out,
        )
        print(json.dumps({"campaign": summary, "field": state}, ensure_ascii=False))
        return 10

    transport = PowerShellWebAITransport(
        driver_path=base / "windows_chatgpt_cdp_driver.ps1",
        recipe_path=recipe_path,
        profile_dir=profile_dir,
        port=effective_port,
        timeout_seconds=args.timeout,
    )

    for name, fn in (
        ("B14", phase_b14),
        ("B18", phase_b18),
        ("B20", phase_b20),
    ):
        print(f"=== {name} ===", flush=True)
        ok, detail = fn(
            transport=transport,
            evidence_dir=evidence_dir,
            provider=provider,
            trial_id=args.trial_id,
        )
        summary["phases"][name] = {"ok": ok, "detail": detail}
        if not ok:
            summary["status"] = f"{name}_FAILED"
            summary["failure_reason"] = detail
            atomic_json(evidence_dir / "FIELD_CAMPAIGN_RESULT.json", summary)
            state = finalize_field(
                evidence_dir,
                trial_id=args.trial_id,
                provider=provider,
                canonical_out=args.canonical_out,
            )
            print(json.dumps({"campaign": summary, "field": state}, ensure_ascii=False))
            return {"B14": 14, "B18": 18, "B20": 20}[name]
        print(f"[PASS] {name}", flush=True)

    state = finalize_field(
        evidence_dir,
        trial_id=args.trial_id,
        provider=provider,
        canonical_out=args.canonical_out,
    )
    summary["ok"] = bool(state["BROWSER_FIELD_VERIFIED"])
    summary["status"] = "B29_B30_FIELD_PASS" if summary["ok"] else "B29_B30_FINALIZE_FAIL"
    summary["failure_reason"] = "" if summary["ok"] else "; ".join(state.get("failures") or [])
    atomic_json(evidence_dir / "FIELD_CAMPAIGN_RESULT.json", summary)
    print(json.dumps({"campaign": summary, "field": state}, ensure_ascii=False))
    return 0 if summary["ok"] else 30


if __name__ == "__main__":
    raise SystemExit(main())
