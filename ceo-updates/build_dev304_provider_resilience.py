from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import zipfile

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE_ZIP = REPO_ROOT / "ceo-updates" / "CEO_1.5.79-rc1-productive-resume-gate.zip"
BUILD_ROOT = pathlib.Path("/tmp/dev304")
OLD_VERSION = "1.5.79-rc1-productive-resume-gate"
NEW_VERSION = "1.5.80-rc1-provider-resilience"
NEW_EPOCH = "dev304-provider-resilience-v1"


def replace_once(path: pathlib.Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def insert_after_unique_line(path: pathlib.Path, stripped_line: str, block: list[str], label: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    matches = [i for i, line in enumerate(lines) if line.strip() == stripped_line]
    if len(matches) != 1:
        raise RuntimeError(f"{label}: expected one line, found {len(matches)}")
    i = matches[0]
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    rendered = []
    for row in block:
        if row == "":
            rendered.append("")
        else:
            rendered.append(indent + row)
    lines[i + 1 : i + 1] = rendered
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def patch_provider_resilience() -> None:
    p = BUILD_ROOT / "ceo_core" / "provider_resilience_v2.py"
    replace_once(
        p,
        'return ProviderRecoveryDecision("quota", True, max(30, backoff), True, True, False)',
        'return ProviderRecoveryDecision("quota", True, max(300, backoff), True, True, False)',
        "quota cooldown",
    )
    replace_once(
        p,
        '        if any(x in text for x in ("401", "403", "invalid api key", "unauthorized", "permission_denied")):\n',
        '        if "no provider can execute" in text or "no compatible provider" in text:\n'
        '            return ProviderRecoveryDecision("provider_unavailable", True, max(300, backoff), False, True, False)\n'
        '        if any(x in text for x in ("401", "403", "invalid api key", "unauthorized", "permission_denied")):\n',
        "provider unavailable classifier",
    )


def patch_gemini_models() -> None:
    p = BUILD_ROOT / "ceo_core" / "providers" / "gemini_interactions.py"
    replace_once(
        p,
        "    PROBE_MODEL_LIMIT = 8\n",
        '    KNOWN_UNAVAILABLE_MODELS = frozenset({"gemini-2.5-flash", "gemini-2.5-flash-lite"})\n'
        "    PROBE_MODEL_LIMIT = 8\n",
        "legacy model constant",
    )
    replace_once(
        p,
        '            candidates.append(name.removeprefix("models/"))\n',
        '            short_name = name.removeprefix("models/")\n'
        '            if short_name in self.KNOWN_UNAVAILABLE_MODELS:\n'
        '                continue\n'
        '            candidates.append(short_name)\n',
        "legacy model discovery filter",
    )


def patch_scheduler() -> None:
    p = BUILD_ROOT / "ceo_core" / "scheduler.py"
    text = p.read_text(encoding="utf-8")

    text = text.replace(
        'RELIABILITY_EPOCH = "dev303-productive-resume-v1"',
        f'RELIABILITY_EPOCH = "{NEW_EPOCH}"',
        1,
    )
    if f'RELIABILITY_EPOCH = "{NEW_EPOCH}"' not in text:
        raise RuntimeError("reliability epoch replacement failed")

    lines = text.splitlines()
    matches = [
        i
        for i, line in enumerate(lines[:-1])
        if line.strip() == "and not any("
        and lines[i + 1].strip() == "is_productive(t, self.state)"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"progress kick anchor: {len(matches)}")
    i = matches[0]
    indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
    lines.insert(i, indent + 'and not bool((self.state.metadata.get("provider_wait_v1") or {}).get("active"))')
    text = "\n".join(lines) + "\n"

    lines = text.splitlines()
    matches = [
        i
        for i, line in enumerate(lines)
        if line.strip() == "except Exception as exc:  # noqa: BLE001 - scheduler isolates worker failure"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"provider exception anchor: {len(matches)}")
    i = matches[0]
    base = lines[i][: len(lines[i]) - len(lines[i].lstrip())] + "    "
    raw = [
        "provider_decision = self.provider_resilience_v2.classify(str(exc), max(1, int(task.attempts)))",
        'wait_categories = {"quota", "provider_unavailable", "model_unavailable", "transient"}',
        "if provider_decision.category in wait_categories:",
        "    retry_seconds = max(30, int(provider_decision.retry_after_seconds or 0))",
        '    global_wait = dict(self.state.metadata.get("provider_wait_v1") or {})',
        '    if provider_decision.category == "quota" or global_wait.get("category") == "quota":',
        "        retry_seconds = max(300, retry_seconds)",
        "    retry_at = time.time() + retry_seconds",
        "    task.status = TaskStatus.BLOCKED",
        "    task.attempts = max(0, int(task.attempts) - 1)",
        "    task.worker_id = None",
        '    task.result = f"WAITING_PROVIDER: {provider_decision.category}; retry in {retry_seconds}s. No recovery budget consumed."',
        '    task.metadata["provider_stage"] = "waiting_provider"',
        '    task.metadata["provider_stage_ts"] = utcnow().isoformat()',
        '    task.metadata["provider_resilience_v2"] = provider_decision.to_dict()',
        '    task.metadata["waiting_provider_v1"] = {',
        '        "active": True,',
        '        "category": provider_decision.category,',
        '        "provider": provider_name,',
        '        "retry_after_seconds": retry_seconds,',
        '        "retry_after_ts": retry_at,',
        '        "error": f"{type(exc).__name__}: {exc}"[:1000],',
        '        "since": utcnow().isoformat(),',
        "    }",
        '    task.metadata["retry_after_ts"] = retry_at',
        '    wait = self.state.metadata.setdefault("provider_wait_v1", {})',
        '    task_ids = list(dict.fromkeys(list(wait.get("task_ids") or []) + [task.id]))',
        "    wait.update({",
        '        "active": True,',
        '        "category": "quota" if global_wait.get("category") == "quota" else provider_decision.category,',
        '        "provider": provider_name,',
        '        "retry_after_seconds": retry_seconds,',
        '        "retry_after_ts": retry_at,',
        '        "task_ids": task_ids[-100:],',
        '        "reason": str(exc)[:1000],',
        '        "updated_at": utcnow().isoformat(),',
        '        "recoveries_consumed": 0,',
        "    })",
        "    if provider_name:",
        "        self.provider_policy.record_failure(",
        "            self.state, provider_name,",
        '            rate_limited=provider_decision.category == "quota",',
        "        )",
        "    self.decision_trace_v3.append(",
        '        self.state, "provider_wait", task=task,',
        '        data={"provider": provider_name, **provider_decision.to_dict()},',
        "    )",
        "    self.evidence_ledger_v2.append(",
        '        self.state, "provider_wait", task=task,',
        '        data={"provider": provider_name, "category": provider_decision.category,',
        '              "retry_after_seconds": retry_seconds, "recovery_budget_consumed": False},',
        "    )",
        "    self._activity_event(",
        '        "provider_wait", task, provider=provider_name,',
        '        detail=f"{provider_decision.category}: espera de proveedor; no cuenta como recuperación",',
        "    )",
        "    return",
        "",
    ]
    rendered = []
    for row in raw:
        if not row:
            rendered.append("")
            continue
        leading = len(row) - len(row.lstrip())
        rendered.append(base + (" " * leading) + row.lstrip())
    lines[i + 1 : i + 1] = rendered
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def patch_productive_truth() -> None:
    p = BUILD_ROOT / "ceo_core" / "productive_truth_v2.py"
    text = p.read_text(encoding="utf-8")
    text = text.replace(
        'if meta.get("epoch") != "dev303-productive-resume-v1":',
        f'if meta.get("epoch") != "{NEW_EPOCH}":',
        1,
    )
    text = text.replace(
        '"epoch": "dev303-productive-resume-v1",',
        f'"epoch": "{NEW_EPOCH}",',
        1,
    )
    anchor = '        status = "working" if running else ("planning" if ready else "idle")\n'
    if text.count(anchor) != 1:
        raise RuntimeError("productive truth status anchor")
    text = text.replace(
        anchor,
        anchor
        + '        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})\n'
        + '        if provider_wait.get("active") and not running:\n'
        + '            status = "waiting_provider"\n'
        + '            stalled = False\n'
        + '            reason = "provider temporarily unavailable: " + str(provider_wait.get("category") or "unavailable")\n',
        1,
    )
    stall = "        elif completed == 0 and recoveries >= self.recovery_trip and internal_active and not running:\n"
    if text.count(stall) != 1:
        raise RuntimeError("productive truth stall anchor")
    text = text.replace(
        stall,
        '        elif provider_wait.get("active") and not running:\n'
        '            pass\n'
        + stall,
        1,
    )
    p.write_text(text, encoding="utf-8")


def patch_observability() -> None:
    p = BUILD_ROOT / "ceo_core" / "observability.py"
    replace_once(
        p,
        '        if productive_truth.get("stalled"):\n'
        '            health = "stalled"\n'
        '            health_reasons = [str(productive_truth.get("reason") or "productive output stalled")]\n',
        '        if productive_truth.get("status") == "waiting_provider":\n'
        '            health = "waiting_provider"\n'
        '            health_reasons = [str(productive_truth.get("reason") or "provider temporarily unavailable")]\n'
        '        elif productive_truth.get("stalled"):\n'
        '            health = "stalled"\n'
        '            health_reasons = [str(productive_truth.get("reason") or "productive output stalled")]\n',
        "observability waiting provider",
    )


def replace_method(text: str, name: str, new_method: str) -> str:
    pat = re.compile(rf"(?ms)^    (?:async )?def {re.escape(name)}\(.*?(?=^    (?:async )?def |^class |\Z)")
    matches = list(pat.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"method {name}: expected one match, found {len(matches)}")
    m = matches[0]
    return text[: m.start()] + new_method.rstrip() + "\n\n" + text[m.end() :]


def patch_work_mode() -> None:
    p = BUILD_ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    text = p.read_text(encoding="utf-8")

    # Local scheduler always has at least a deterministic local worker.
    router = '''    def _router(self):
        local_goal_lock = self.GoalLockLocalProviderV1()
        providers = [local_goal_lock]
        if self.execution_enabled and self.gemini_key:
            transport = self.GeminiInteractionsTransport(api_key=self.gemini_key, model=self.gemini_model or "auto")
            providers.insert(0, self.AIWorkerProvider(transport))
        return self.MultiProviderRouter(providers)
'''
    text = replace_method(text, "_router", router)

    # Reliability epoch is persisted before any provider validation can gate scheduler creation.
    anchor = "                state = store.prepare_for_resume(state)\n                self.state = state\n"
    if text.count(anchor) != 1:
        raise RuntimeError(f"pre-scheduler state anchor: {text.count(anchor)}")
    text = text.replace(
        anchor,
        anchor
        + "                from ceo_core.scheduler import _apply_reliability_epoch_migration\n"
        + "                pre_scheduler_migration = _apply_reliability_epoch_migration(state)\n"
        + '                state.metadata["pre_scheduler_reliability_migration"] = pre_scheduler_migration\n'
        + "                if pre_scheduler_migration.get(\"changed\"):\n"
        + "                    store.save(state)\n"
        + "                    self.projects.touch(state)\n",
        1,
    )

    # Existing project gets a scheduler even when Gemini is unavailable.
    text = text.replace(
        "                if self.execution_enabled and not state.completed_at and not state.cancelled_at and not state.metadata.get(\"operator_cancelled\"):\n",
        "                if not state.paused and not state.completed_at and not state.cancelled_at and not state.metadata.get(\"operator_cancelled\"):\n",
        1,
    )

    # New objectives are not globally paused just because the external provider is unavailable.
    new_goal_old = (
        "        if not self.execution_enabled:\n"
        "            state.paused = True\n"
        '            state.metadata["execution_disabled_reason"] = "Gemini API key was not provided for this session"\n'
    )
    new_goal_new = (
        "        if not self.execution_enabled:\n"
        '            state.metadata["execution_disabled_reason"] = self.gemini_validation_error or "External AI provider unavailable"\n'
        '            state.metadata["provider_wait_v1"] = {\n'
        '                "active": True, "category": "quota" if "QUOTA" in str(self.gemini_key_status or "").upper() else "provider_unavailable",\n'
        '                "provider": "gemini-interactions", "retry_after_seconds": 300,\n'
        '                "retry_after_ts": time.time() + 300, "recoveries_consumed": 0,\n'
        '                "reason": self.gemini_validation_error or "External AI provider unavailable",\n'
        '                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),\n'
        "            }\n"
    )
    if text.count(new_goal_old) != 1:
        raise RuntimeError(f"new goal provider-gate anchor: {text.count(new_goal_old)}")
    text = text.replace(new_goal_old, new_goal_new, 1)

    # Always create scheduler for new goal.
    new_goal_sched = (
        "        if self.execution_enabled:\n"
        "            self.router = self._router()\n"
        "            self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)\n"
        "            self.scheduler.start()\n"
    )
    new_goal_sched_new = (
        "        self.router = self._router()\n"
        "        self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)\n"
        "        self.scheduler.start()\n"
    )
    if text.count(new_goal_sched) != 1:
        raise RuntimeError(f"new goal scheduler anchor: {text.count(new_goal_sched)}")
    text = text.replace(new_goal_sched, new_goal_sched_new, 1)

    # Revalidation state.
    flag = "        self.provider_validation_in_progress = False\n"
    if text.count(flag) != 1:
        raise RuntimeError(f"provider validation flag anchor: {text.count(flag)}")
    text = text.replace(
        flag,
        flag
        + "        self._next_provider_revalidation_ts = 0.0\n"
        + "        self._provider_revalidation_interval_seconds = 300.0\n",
        1,
    )

    # Background revalidation uses the existing event-loop call bridge.
    method = '''    def start_stored_provider_revalidation_background(self) -> bool:
        if self.provider_validation_in_progress:
            return False
        now = time.time()
        if now < float(self._next_provider_revalidation_ts or 0.0):
            return False
        self._next_provider_revalidation_ts = now + float(self._provider_revalidation_interval_seconds)
        self.provider_validation_in_progress = True

        def _runner():
            try:
                self.call(self.revalidate_stored_gemini(), timeout=90)
            except Exception as exc:
                self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
            finally:
                self.provider_validation_in_progress = False

        threading.Thread(target=_runner, name="ceo-provider-revalidation", daemon=True).start()
        return True
'''
    if "    def start_stored_provider_revalidation_background(" not in text:
        idx = text.find("    def _run_loop(self):")
        if idx < 0:
            raise RuntimeError("_run_loop anchor missing")
        text = text[:idx] + method + "\n" + text[idx:]

    # Recognized quota/model block: record explicit provider wait and keep local scheduler healthy.
    quota_anchor = (
        '                    state.metadata["execution_disabled_reason"] = self.gemini_validation_error\n'
        "                    self.projects.store(state.id).save(state)\n"
        "                return await self.snapshot()\n"
    )
    quota_new = (
        '                    state.metadata["execution_disabled_reason"] = self.gemini_validation_error\n'
        '                    state.metadata["provider_wait_v1"] = {\n'
        '                        "active": True,\n'
        '                        "category": "quota" if "QUOTA" in status.upper() else "provider_unavailable",\n'
        '                        "provider": "gemini-interactions",\n'
        '                        "retry_after_seconds": int(self._provider_revalidation_interval_seconds),\n'
        '                        "retry_after_ts": time.time() + float(self._provider_revalidation_interval_seconds),\n'
        '                        "reason": self.gemini_validation_error,\n'
        '                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),\n'
        '                        "recoveries_consumed": 0,\n'
        "                    }\n"
        "                    self.projects.store(state.id).save(state)\n"
        "                    await self._ensure_scheduler_health()\n"
        "                self._next_provider_revalidation_ts = time.time() + float(self._provider_revalidation_interval_seconds)\n"
        "                return await self.snapshot()\n"
    )
    if text.count(quota_anchor) != 1:
        raise RuntimeError(f"recognized quota anchor: {text.count(quota_anchor)}")
    text = text.replace(quota_anchor, quota_new, 1)

    # Successful validation clears waits and makes provider available to current scheduler.
    success_anchor = '            state.metadata.pop("execution_disabled_reason", None)\n'
    if text.count(success_anchor) != 1:
        raise RuntimeError(f"success wait clear anchor: {text.count(success_anchor)}")
    success_block = (
        success_anchor
        + '            state.metadata.pop("provider_wait_v1", None)\n'
        + "            from ceo_core.models import TaskStatus\n"
        + "            for waiting_task in state.leaf_tasks:\n"
        + '                if waiting_task.metadata.pop("waiting_provider_v1", None) is not None:\n'
        + '                    waiting_task.metadata.pop("retry_after_ts", None)\n'
        + "                    if waiting_task.status == TaskStatus.BLOCKED:\n"
        + "                        waiting_task.status = TaskStatus.WAITING\n"
    )
    text = text.replace(success_anchor, success_block, 1)

    # Replace scheduler start-on-success with start-or-hot-swap.
    success_sched = (
        "            if self.scheduler is None and not state.completed_at and not state.cancelled_at and not state.metadata.get(\"operator_cancelled\"):\n"
        "                self.router = self._router()\n"
        "                self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)\n"
        "                self.scheduler.start()\n"
        "        return await self.snapshot()\n"
    )
    success_sched_new = (
        "            self.router = self._router()\n"
        "            if self.scheduler is None and not state.completed_at and not state.cancelled_at and not state.metadata.get(\"operator_cancelled\"):\n"
        "                self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)\n"
        "                self.scheduler.start()\n"
        "            elif self.scheduler is not None:\n"
        "                self.scheduler.router = self.router\n"
        "                self.scheduler.graph.refresh(state)\n"
        "            self._next_provider_revalidation_ts = 0.0\n"
        "        return await self.snapshot()\n"
    )
    if text.count(success_sched) != 1:
        raise RuntimeError(f"success scheduler hot-swap anchor: {text.count(success_sched)}")
    text = text.replace(success_sched, success_sched_new, 1)

    # Scheduler health is independent from provider availability and triggers bounded revalidation.
    health_anchor = (
        "    async def _ensure_scheduler_health(self):\n"
        "        state = self._state_obj()\n"
        "        if state is None or not self.execution_enabled or state.paused or state.completed_at is not None or state.cancelled_at is not None or state.metadata.get(\"operator_cancelled\"):\n"
    )
    health_new = (
        "    async def _ensure_scheduler_health(self):\n"
        "        state = self._state_obj()\n"
        "        if (\n"
        "            self.gemini_key_recognized and not self.execution_enabled\n"
        "            and not self.provider_validation_in_progress\n"
        "            and time.time() >= float(self._next_provider_revalidation_ts or 0.0)\n"
        "        ):\n"
        "            self.start_stored_provider_revalidation_background()\n"
        "        if state is None or state.paused or state.completed_at is not None or state.cancelled_at is not None or state.metadata.get(\"operator_cancelled\"):\n"
    )
    if text.count(health_anchor) != 1:
        raise RuntimeError(f"scheduler health anchor: {text.count(health_anchor)}")
    text = text.replace(health_anchor, health_new, 1)

    # Snapshot explicitly distinguishes provider wait.
    snap_anchor = (
        "        if self.scheduler is not None:\n"
        "            operational_status = self.scheduler.operational_status()\n"
    )
    if text.count(snap_anchor) != 1:
        raise RuntimeError(f"snapshot status anchor: {text.count(snap_anchor)}")
    text = text.replace(
        snap_anchor,
        '        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})\n'
        '        if provider_wait.get("active") and scheduler_alive:\n'
        '            operational_status = "ESPERANDO PROVEEDOR"\n'
        "        elif self.scheduler is not None:\n"
        "            operational_status = self.scheduler.operational_status()\n",
        1,
    )

    text = text.replace(
        "stalled:'ATASCADO',attention:'TE NECESITA'",
        "stalled:'ATASCADO',waiting_provider:'ESPERANDO PROVEEDOR',attention:'TE NECESITA'",
        1,
    )
    text = text.replace(
        "else if(rawLevel==='stalled'){attBox.textContent='CEO detectó producción nula: está cambiando de estrategia; actividad de proveedor no cuenta como progreso.'}",
        "else if(rawLevel==='waiting_provider'){attBox.textContent='Proveedor temporalmente no disponible. CEO mantiene el scheduler local y reintentará sin consumir recuperaciones.'}else if(rawLevel==='stalled'){attBox.textContent='CEO detectó producción nula: está cambiando de estrategia; actividad de proveedor no cuenta como progreso.'}",
        1,
    )

    text = text.replace(OLD_VERSION, NEW_VERSION)
    p.write_text(text, encoding="utf-8")


def update_contract() -> None:
    p = BUILD_ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(p.read_text(encoding="utf-8"))
    contract["app_version"] = NEW_VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in list(hashes):
        fp = BUILD_ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract file: {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    p.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE_ZIP.is_file():
        raise RuntimeError(f"missing base ZIP: {BASE_ZIP}")
    shutil.rmtree(BUILD_ROOT, ignore_errors=True)
    BUILD_ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE_ZIP) as zf:
        zf.extractall(BUILD_ROOT)

    patch_provider_resilience()
    patch_gemini_models()
    patch_scheduler()
    patch_productive_truth()
    patch_observability()
    patch_work_mode()

    bootstrap = BUILD_ROOT / "scripts" / "install_windows_bootstrap.py"
    if bootstrap.exists():
        bootstrap.write_text(bootstrap.read_text(encoding="utf-8").replace(OLD_VERSION, NEW_VERSION), encoding="utf-8")

    update_contract()
    print(json.dumps({"ok": True, "root": str(BUILD_ROOT), "version": NEW_VERSION}, indent=2))


if __name__ == "__main__":
    main()
