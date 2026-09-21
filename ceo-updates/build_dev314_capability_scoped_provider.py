from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.89-rc1-deterministic-completion.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV314_BUILD_ROOT", "/tmp/ceo-dev314-capability-provider"))
OLD_VERSION = "1.5.89-rc1-deterministic-completion"
VERSION = "1.5.90-rc1-capability-scoped-provider"


def patch_autonomous_loop() -> None:
    p = ROOT / "ceo_core" / "autonomous_loop.py"
    s = p.read_text(encoding="utf-8")

    anchor = '''        productive_runnable = [
            t for t in state.leaf_tasks
            if is_productive(t, state)
            and t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY}
        ]
        if productive_runnable:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            return {
                "status": "productive_work_available",
                "created": 0,
                "changed": 0,
                "productive_task_ids": [t.id for t in productive_runnable[:20]],
            }

        internal_runnable = [
'''
    replacement = '''        productive_runnable = [
            t for t in state.leaf_tasks
            if is_productive(t, state)
            and t.status in {TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.RETRY}
        ]
        if productive_runnable:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            return {
                "status": "productive_work_available",
                "created": 0,
                "changed": 0,
                "productive_task_ids": [t.id for t in productive_runnable[:20]],
            }

        # Provider scarcity is not a deadlock. If every hard productive block is
        # explicitly a provider wait, hold position without creating recovery work.
        # Local/control work remains eligible because the branch above wins whenever
        # any productive unit is runnable.
        provider_waiting = [
            t for t in state.leaf_tasks
            if is_productive(t, state)
            and t.status in {TaskStatus.BLOCKED, TaskStatus.WAITING}
            and bool((t.metadata.get("waiting_provider_v1") or {}).get("active"))
        ]
        non_provider_hard = [
            t for t in state.leaf_tasks
            if is_productive(t, state)
            and t.status in {TaskStatus.BLOCKED, TaskStatus.FAILED, TaskStatus.NEEDS_REVIEW}
            and not bool((t.metadata.get("waiting_provider_v1") or {}).get("active"))
        ]
        if provider_waiting and not non_provider_hard:
            state.metadata["autonomy_stall_cycles"] = 0
            state.metadata.pop("autonomy_stalled", None)
            state.metadata["provider_capability_wait_v1"] = {
                "active": True,
                "task_ids": [t.id for t in provider_waiting[:100]],
                "count": len(provider_waiting),
                "recoveries_consumed": 0,
                "reason": "No compatible external provider is currently available; local core remains active.",
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            return {
                "status": "waiting_external_provider_capability",
                "created": 0,
                "changed": 0,
                "task_ids": [t.id for t in provider_waiting[:20]],
                "recoveries_consumed": 0,
            }
        elif state.metadata.get("provider_capability_wait_v1"):
            state.metadata.pop("provider_capability_wait_v1", None)

        internal_runnable = [
'''
    if s.count(anchor) != 1:
        raise RuntimeError(f"provider wait watchdog anchor={s.count(anchor)}")
    s = s.replace(anchor, replacement, 1)
    p.write_text(s, encoding="utf-8")


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    # Existing projects must recover their local scheduler independently of Gemini.
    init_anchor = '''                if migration.get("changed"):
                    state.metadata["grounded_completion_gate_migration"] = migration
                    store.save(state)
                    self.projects.touch(state)
                if not state.paused and not state.completed_at and not state.cancelled_at and not state.metadata.get("operator_cancelled"):
                    self.router = self._router()
                    self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
                    self.scheduler.start()
'''
    init_new = '''                if migration.get("changed"):
                    state.metadata["grounded_completion_gate_migration"] = migration
                    store.save(state)
                    self.projects.touch(state)

                # DEV314: provider availability is capability-scoped, not a global
                # pause. Migrate pauses that were created only because Gemini was
                # unavailable; preserve explicit operator pauses.
                legacy_provider_pause = bool(
                    state.paused
                    and not state.metadata.get("operator_paused_v1")
                    and (
                        (state.metadata.get("provider_wait_v1") or {}).get("active")
                        or state.metadata.get("execution_disabled_reason")
                    )
                )
                if legacy_provider_pause:
                    state.paused = False
                    state.metadata["dev314_provider_pause_migrated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    store.save(state)
                    self.projects.touch(state)

                if not state.paused and not state.completed_at and not state.cancelled_at and not state.metadata.get("operator_cancelled"):
                    self.router = self._router()
                    self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
                    self.scheduler.start()
'''
    if s.count(init_anchor) != 1:
        raise RuntimeError(f"initialize provider scope anchor={s.count(init_anchor)}")
    s = s.replace(init_anchor, init_new, 1)

    # New project creation is deterministic through the baseline planner. Let it be
    # created even when Gemini is absent; AI-dependent tasks will wait safely.
    start_guard = '''    async def start_project(self, body: dict[str, Any]):
        if not self.execution_enabled:
            raise RuntimeError("Gemini no está validado. Actívalo primero; no se creará un proyecto que parezca estar trabajando cuando está pausado.")
        goal_text = str(body.get("goal") or "").strip()
'''
    start_new = '''    async def start_project(self, body: dict[str, Any]):
        goal_text = str(body.get("goal") or "").strip()
'''
    if s.count(start_guard) != 1:
        raise RuntimeError(f"start project global provider guard={s.count(start_guard)}")
    s = s.replace(start_guard, start_new, 1)

    # Manual pause becomes explicit durable operator state.
    pause_anchor = '''    async def pause(self, paused: bool):
        state = self._state_obj()
        if state is None:
            return await self.snapshot()
        state.paused = bool(paused)
'''
    pause_new = '''    async def pause(self, paused: bool):
        state = self._state_obj()
        if state is None:
            return await self.snapshot()
        state.paused = bool(paused)
        if paused:
            state.metadata["operator_paused_v1"] = True
            state.metadata["operator_paused_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        else:
            state.metadata.pop("operator_paused_v1", None)
            state.metadata.pop("operator_paused_at", None)
'''
    if s.count(pause_anchor) != 1:
        raise RuntimeError(f"manual pause anchor={s.count(pause_anchor)}")
    s = s.replace(pause_anchor, pause_new, 1)

    activate_anchor = '''        state.paused = not self.execution_enabled
        store.save(state)
        self.projects.touch(state)
        self.state = state
        if self.execution_enabled and state.completed_at is None:
            self.router = self._router()
            self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
            self.scheduler.start()
'''
    activate_new = '''        provider_induced_pause = bool(
            state.paused
            and not state.metadata.get("operator_paused_v1")
            and (
                (state.metadata.get("provider_wait_v1") or {}).get("active")
                or state.metadata.get("execution_disabled_reason")
            )
        )
        if provider_induced_pause:
            state.paused = False
            state.metadata["dev314_provider_pause_migrated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        store.save(state)
        self.projects.touch(state)
        self.state = state
        if not state.paused and state.completed_at is None:
            self.router = self._router()
            self.scheduler = self.ContinuousScheduler(state, None, store, graph=self.Graph(), router=self.router)
            self.scheduler.start()
'''
    if s.count(activate_anchor) != 1:
        raise RuntimeError(f"activate project provider scope anchor={s.count(activate_anchor)}")
    s = s.replace(activate_anchor, activate_new, 1)

    # Resume local scheduler even if external AI is unavailable.
    resume_anchor = '''            if path == "/api/resume":
                if not self.engine.execution_enabled:
                    return self.json({"error": "Gemini no está validado en esta sesión. Actívalo desde la interfaz antes de reanudar."}, 409)
                return self.json(self.engine.call(self.engine.pause(False)))
'''
    resume_new = '''            if path == "/api/resume":
                return self.json(self.engine.call(self.engine.pause(False)))
'''
    if s.count(resume_anchor) != 1:
        raise RuntimeError(f"resume provider guard anchor={s.count(resume_anchor)}")
    s = s.replace(resume_anchor, resume_new, 1)

    # UI: core/scheduler activity is distinct from Gemini availability.
    working_anchor = """const working=!!(s.active&&live&&schedulerAlive&&['TRABAJANDO','PLANIFICANDO','VERIFICANDO','CORRIGIENDO'].includes(real));
"""
    working_new = """const working=!!(s.active&&schedulerAlive&&['TRABAJANDO','PLANIFICANDO','VERIFICANDO','CORRIGIENDO'].includes(real));
"""
    if s.count(working_anchor) != 1:
        raise RuntimeError(f"working UI anchor={s.count(working_anchor)}")
    s = s.replace(working_anchor, working_new, 1)

    controls_anchor = """$('power').value=s.power_percent??30;$('powerLabel').textContent=$('power').value+'%';const hasActive=!!s.active;$('pauseBtn').disabled=!hasActive||!!s.paused;$('resumeBtn').disabled=!hasActive||!s.paused||!live;$('cancelBtn').disabled=!hasActive;$('startBtn').disabled=!live;$('startBtn').title=live?'Iniciar trabajo real':'Primero activa y valida Gemini';
"""
    controls_new = """$('power').value=s.power_percent??30;$('powerLabel').textContent=$('power').value+'%';const hasActive=!!s.active;$('pauseBtn').disabled=!hasActive||!!s.paused;$('resumeBtn').disabled=!hasActive||!s.paused;$('cancelBtn').disabled=!hasActive;$('startBtn').disabled=false;$('startBtn').title=live?'Iniciar trabajo real':'Crear proyecto; las tareas que necesiten Gemini esperarán al proveedor';
"""
    if s.count(controls_anchor) != 1:
        raise RuntimeError(f"controls provider scope anchor={s.count(controls_anchor)}")
    s = s.replace(controls_anchor, controls_new, 1)

    banner_anchor = """else if(!live){$('actionBanner').className='banner warnb';$('actionBanner').textContent='Gemini no está activo. CEO no está trabajando.'}
"""
    banner_new = """else if(s.active&&!live&&schedulerAlive){$('actionBanner').className='banner infob';$('actionBanner').textContent='ℹ Núcleo de CEO activo. Gemini no está disponible: las tareas que requieren IA esperan sin consumir recuperaciones; el trabajo local/determinista continúa.'}
else if(!live){$('actionBanner').className='banner warnb';$('actionBanner').textContent='Gemini no está disponible. El núcleo local sigue sano; configura el proveedor cuando quieras ejecutar tareas que requieran IA.'}
"""
    if s.count(banner_anchor) != 1:
        raise RuntimeError(f"provider banner scope anchor={s.count(banner_anchor)}")
    s = s.replace(banner_anchor, banner_new, 1)

    start_js_anchor = """async function startNewProject(){const goal=$('goal').value.trim();const name=$('name').value.trim()||null;const status=$('startStatus');if(!state?.execution_enabled){$('actionBanner').className='banner errb';$('actionBanner').textContent='No iniciado: primero activa y valida Gemini.';if(status)status.textContent='Gemini no está activo.';return}if(goal.length<3){if(status)status.textContent='Escribe un objetivo de al menos 3 caracteres.';return}let slow=setTimeout(()=>{if(status)status.textContent='Cerrando de forma segura el proyecto anterior y preparando el nuevo…';},1800);
"""
    start_js_new = """async function startNewProject(){const goal=$('goal').value.trim();const name=$('name').value.trim()||null;const status=$('startStatus');if(goal.length<3){if(status)status.textContent='Escribe un objetivo de al menos 3 caracteres.';return}let slow=setTimeout(()=>{if(status)status.textContent='Cerrando de forma segura el proyecto anterior y preparando el nuevo…';},1800);
"""
    if s.count(start_js_anchor) != 1:
        raise RuntimeError(f"start JS provider guard anchor={s.count(start_js_anchor)}")
    s = s.replace(start_js_anchor, start_js_new, 1)

    # Operational status should not let a stale global provider-wait hide active
    # local scheduler work.
    op_anchor = '''        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})
        if provider_wait.get("active") and scheduler_alive:
            operational_status = "ESPERANDO PROVEEDOR"
        elif self.scheduler is not None:
            operational_status = self.scheduler.operational_status()
'''
    op_new = '''        provider_wait = dict(state.metadata.get("provider_wait_v1") or {})
        scheduler_status = self.scheduler.operational_status() if self.scheduler is not None else None
        if scheduler_status in {"TRABAJANDO", "VERIFICANDO", "CORRIGIENDO"}:
            operational_status = scheduler_status
        elif provider_wait.get("active") and scheduler_alive:
            operational_status = "ESPERANDO PROVEEDOR"
        elif self.scheduler is not None:
            operational_status = scheduler_status
'''
    if s.count(op_anchor) != 1:
        raise RuntimeError(f"operational provider scope anchor={s.count(op_anchor)}")
    s = s.replace(op_anchor, op_new, 1)

    # Expose the distinction explicitly for UI/remote clients. Patch active and
    # inactive snapshots separately so inactive state never references scheduler_alive.
    inactive_snap_anchor = '''                "active": False,
                "execution_enabled": self.execution_enabled,
                "provider_mode": self.provider_mode,
'''
    inactive_snap_new = '''                "active": False,
                "execution_enabled": self.execution_enabled,
                "core_execution_available": bool(self.loop.is_running() and self.thread.is_alive()),
                "external_ai_available": bool(self.execution_enabled),
                "provider_mode": self.provider_mode,
'''
    if s.count(inactive_snap_anchor) != 1:
        raise RuntimeError(f"inactive snapshot provider scope anchor={s.count(inactive_snap_anchor)}")
    s = s.replace(inactive_snap_anchor, inactive_snap_new, 1)

    active_snap_anchor = '''            "active": True,
            "project_id": state.id,
            "execution_enabled": self.execution_enabled,
            "provider_mode": self.provider_mode,
'''
    active_snap_new = '''            "active": True,
            "project_id": state.id,
            "execution_enabled": self.execution_enabled,
            "core_execution_available": bool(scheduler_alive),
            "external_ai_available": bool(self.execution_enabled),
            "provider_mode": self.provider_mode,
'''
    if s.count(active_snap_anchor) != 1:
        raise RuntimeError(f"active snapshot provider scope anchor={s.count(active_snap_anchor)}")
    s = s.replace(active_snap_anchor, active_snap_new, 1)

    p.write_text(s, encoding="utf-8")


def update_contract() -> None:
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in contract["required_paths"]:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    cpath.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base {BASE}")
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    patch_autonomous_loop()
    patch_work_mode()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "invariants": [
            "core_execution_is_independent_of_external_ai_availability",
            "unsupported_ai_tasks_wait_without_recovery_budget",
            "local_eligible_work_continues_during_provider_outage",
            "provider_wait_does_not_trigger_recovery_churn",
            "manual_pause_remains_authoritative",
            "new_and_resumed_projects_can_exist_with_ai_tasks_waiting",
            "dev311_to_dev313_hardening_inherited",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
