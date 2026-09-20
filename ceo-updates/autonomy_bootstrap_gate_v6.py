from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

GATE1_PATH = pathlib.Path(__file__).with_name("autonomy_bootstrap_gate_v1.py").resolve()
spec = importlib.util.spec_from_file_location("bootstrap_gate_v1_shared", GATE1_PATH)
gate1 = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate1)

ROOT = gate1.ROOT
ARTIFACT_DIR = pathlib.Path(os.environ.get("CEO_GATE_ARTIFACTS", "/tmp/ceo-autonomy-gate-artifacts")).resolve()
TaskStatus = gate1.TaskStatus


class SelfDevProvider(gate1.GateProvider):
    name = "autonomy-bootstrap-selfdev"

    def __init__(self, engine_getter, sandbox: pathlib.Path, original_hash: str):
        super().__init__(engine_getter)
        self.sandbox = sandbox
        self.target = sandbox / "sandbox_selfdev.py"
        self.report = sandbox / "SELF_DEV_REPORT.md"
        self.test_report = sandbox / "SELF_DEV_TEST.json"
        self.original_hash = original_hash
        self.edit_applied = False
        self.compile_passed = False
        self.functional_passed = False

    def _run_validation(self) -> None:
        compile_proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(self.target)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.compile_passed = compile_proc.returncode == 0
        if not self.compile_passed:
            raise RuntimeError("sandbox compile failed: " + (compile_proc.stderr or compile_proc.stdout))

        code = (
            "import importlib.util, pathlib;"
            f"p=pathlib.Path(r'{str(self.target)}');"
            "s=importlib.util.spec_from_file_location('sandbox_selfdev',p);"
            "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
            "assert m.bootstrap_probe('CEO')=='CEO:BOOTSTRAP_OK';"
            "print('FUNCTIONAL_PASS')"
        )
        run_proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.functional_passed = run_proc.returncode == 0 and "FUNCTIONAL_PASS" in run_proc.stdout
        if not self.functional_passed:
            raise RuntimeError("sandbox functional check failed: " + (run_proc.stderr or run_proc.stdout))

        self.test_report.write_text(
            json.dumps(
                {
                    "compile_passed": self.compile_passed,
                    "functional_passed": self.functional_passed,
                    "target": str(self.target),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    async def execute(self, request):
        engine = self.engine_getter()
        task = engine.state.tasks[request.work_unit.id]

        if task.metadata.get("goal_continuity_audit"):
            return await super().execute(request)

        if task.metadata.get("verification_task"):
            if self.edit_applied:
                self._run_validation()
            return await super().execute(request)

        title = task.title.lower()
        if "execution" in title and not self.edit_applied:
            before = self.target.read_text(encoding="utf-8")
            addition = (
                "\n\ndef bootstrap_probe(name: str) -> str:\n"
                "    \"\"\"Deterministic self-development sandbox probe.\"\"\"\n"
                "    clean = str(name).strip() or \"CEO\"\n"
                "    return f\"{clean}:BOOTSTRAP_OK\"\n"
            )
            if "def bootstrap_probe(" not in before:
                self.target.write_text(before.rstrip() + addition + "\n", encoding="utf-8")
            self.edit_applied = True
            self._run_validation()

            self.report.write_text(
                "# CEO Self-Development Sandbox Report\n\n"
                "SELF DEVELOPMENT PASS\n\n"
                "- Scope: isolated sandbox only.\n"
                "- Change: added bootstrap_probe(name).\n"
                "- Compile check: PASS.\n"
                "- Functional check: PASS.\n"
                "- Production mutation: forbidden and not performed.\n",
                encoding="utf-8",
            )

            payload = {
                "status": "complete",
                "reason": "Sandbox source changed and compile/functional validation passed.",
                "confidence": 1.0,
            }
            self.calls += 1
            return gate1.WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=True,
                text=(
                    f"Sandbox self-development change completed. Report: {self.report}\n"
                    "<CEO_RESULT>" + json.dumps(payload) + "</CEO_RESULT>"
                ),
                artifacts=[str(self.target), str(self.report), str(self.test_report)],
                metadata={
                    "sources": ["sandbox:selfdev-target", "sandbox:selfdev-functional-test"],
                    "sandbox_only": True,
                    "compile_passed": True,
                    "functional_passed": True,
                },
                conversation_id=request.conversation_id or f"selfdev-{task.id}",
            )

        return await super().execute(request)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    os.environ.setdefault("CEO_NO_BROWSER", "1")
    work = gate1.load_work_mode()

    with tempfile.TemporaryDirectory(prefix="ceo-selfdev-sandbox-") as td:
        sandbox = pathlib.Path(td)
        source_original = ROOT / "ceo_core" / "goal_engine.py"
        source_copy = sandbox / "sandbox_selfdev.py"
        shutil.copy2(source_original, source_copy)
        original_hash = sha256(source_original)
        sandbox_initial_hash = sha256(source_copy)

        engine = work.CEOEngine(None)
        provider = SelfDevProvider(lambda: engine, sandbox, original_hash)
        engine.execution_enabled = True
        engine.provider_mode = "autonomy-bootstrap-selfdev"
        engine.gemini_key_status = "GATE_PROVIDER"
        engine.gemini_validation_error = None
        engine._router = lambda: gate1.FixedWorkerRouter(provider)

        goal = (
            "In an isolated sandbox copy of CEO, add a small pure helper bootstrap_probe(name), "
            "compile it, run a functional check, and create SELF_DEV_REPORT.md containing "
            "SELF DEVELOPMENT PASS. Do not modify production."
        )

        started = time.monotonic()
        engine.call(
            engine.start_project(
                {
                    "goal": goal,
                    "name": "Autonomy Bootstrap Gate 6 Self Development",
                    "power_percent": 20,
                }
            ),
            timeout=60,
        )

        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            engine.call(engine.snapshot(), timeout=15)
            state = engine.state
            if state.completed_at is not None and state.metadata.get("goal_audit_passed"):
                break
            time.sleep(0.15)

        state = engine.state
        original_hash_after = sha256(source_original)
        sandbox_hash_after = sha256(source_copy)
        report_text = provider.report.read_text(encoding="utf-8") if provider.report.is_file() else ""
        test_json = json.loads(provider.test_report.read_text(encoding="utf-8")) if provider.test_report.is_file() else {}

        result = {
            "passed_completion": state.completed_at is not None and bool(state.metadata.get("goal_audit_passed")),
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "operator_state": state.metadata.get("operator_productivity_state"),
            "worker_recoveries": int(state.metadata.get("worker_recoveries", 0) or 0),
            "unresolved_human_decisions": len([d for d in state.decisions.values() if not d.resolved]),
            "provider_calls": provider.calls,
            "audit_calls": provider.audit_calls,
            "decomposition_profile": state.metadata.get("decomposition_profile"),
            "edit_applied": provider.edit_applied,
            "compile_passed": provider.compile_passed,
            "functional_passed": provider.functional_passed,
            "sandbox_changed": sandbox_initial_hash != sandbox_hash_after,
            "production_unchanged": original_hash == original_hash_after,
            "report_exists": provider.report.is_file(),
            "report_marker": "SELF DEVELOPMENT PASS" in report_text,
            "test_report": test_json,
        }
        print("AUTONOMY_BOOTSTRAP_GATE_6_REPORT")
        print(json.dumps(result, indent=2, default=str))

        try:
            engine.call(engine.shutdown(), timeout=20)
        except Exception as exc:
            print("shutdown_warning", type(exc).__name__, str(exc))

        assert result["passed_completion"], "self-development objective did not close"
        assert result["edit_applied"], "CEO did not apply sandbox change"
        assert result["compile_passed"], "sandbox compile validation failed"
        assert result["functional_passed"], "sandbox functional validation failed"
        assert result["sandbox_changed"], "sandbox source was not changed"
        assert result["production_unchanged"], "production source was modified"
        assert result["report_exists"] and result["report_marker"], "self-development report missing"
        assert result["worker_recoveries"] <= 2, "self-development recovery budget exceeded"
        assert result["unresolved_human_decisions"] == 0, "self-development required human decision"
        assert result["provider_calls"] <= 15, f"self-development used too many provider calls: {provider.calls}"

        print("AUTONOMY_BOOTSTRAP_GATE_6_PASS")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
