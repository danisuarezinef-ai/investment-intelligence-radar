from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.85-rc1-closure-convergence.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV310_BUILD_ROOT", "/tmp/ceo-dev310-provider-session"))
OLD_VERSION = "1.5.85-rc1-closure-convergence"
VERSION = "1.5.86-rc1-provider-session-integrity"


def replace_once(path: pathlib.Path, old: str, new: str, label: str) -> None:
    s = path.read_text(encoding="utf-8")
    count = s.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")


def patch_gemini_transport() -> None:
    p = ROOT / "ceo_core" / "providers" / "gemini_interactions.py"
    s = p.read_text(encoding="utf-8")
    if s.count("    PROBE_MODEL_LIMIT = 8\n") != 1:
        raise RuntimeError("probe model limit anchor missing")
    s = s.replace("    PROBE_MODEL_LIMIT = 8\n", "    PROBE_MODEL_LIMIT = 2\n", 1)

    old_sig = """        max_output_tokens: int = 512,
    ) -> tuple[dict[str, Any], httpx.Response]:
"""
    new_sig = """        max_output_tokens: int = 512,
        attempts: int | None = None,
    ) -> tuple[dict[str, Any], httpx.Response]:
"""
    if s.count(old_sig) != 1:
        raise RuntimeError(f"generate signature anchor={s.count(old_sig)}")
    s = s.replace(old_sig, new_sig, 1)

    old_req = """            payload={
                "contents": contents,
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": int(max_output_tokens)},
            },
        )
"""
    new_req = """            payload={
                "contents": contents,
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": int(max_output_tokens)},
            },
            attempts=attempts,
        )
"""
    if s.count(old_req) != 1:
        raise RuntimeError(f"generate request anchor={s.count(old_req)}")
    s = s.replace(old_req, new_req, 1)

    old_probe_call = """                        contents=[{"role": "user", "parts": self._parts("Reply exactly with OK.")}],
                        max_output_tokens=8,
                    )
"""
    new_probe_call = """                        contents=[{"role": "user", "parts": self._parts("Reply exactly with OK.")}],
                        max_output_tokens=8,
                        attempts=1,
                    )
"""
    if s.count(old_probe_call) != 1:
        raise RuntimeError(f"probe call anchor={s.count(old_probe_call)}")
    s = s.replace(old_probe_call, new_probe_call, 1)

    # Authentication evidence: a successful model listing is enough to distinguish
    # credential acceptance from generation availability/quota.
    s = s.replace(
        '{"ok": False, "status": "NO_GENERATION_MODEL", "detail": "No generateContent model visible"}',
        '{"ok": False, "status": "NO_GENERATION_MODEL", "detail": "No generateContent model visible", "authenticated": True, "models_visible": 0}',
        1,
    )
    success_anchor = '''                        "verified_generation": True,
                        "verified_at_monotonic": now,
'''
    success_new = '''                        "verified_generation": True,
                        "authenticated": True,
                        "verified_at_monotonic": now,
'''
    if s.count(success_anchor) != 1:
        raise RuntimeError(f"probe success auth anchor={s.count(success_anchor)}")
    s = s.replace(success_anchor, success_new, 1)

    failure_anchor = '''                "models_visible": len(models),
                "models_tested": min(len(models), min(self.PROBE_MODEL_LIMIT, self.max_models)),
'''
    failure_new = '''                "models_visible": len(models),
                "models_tested": min(len(models), min(self.PROBE_MODEL_LIMIT, self.max_models)),
                "authenticated": True,
'''
    if s.count(failure_anchor) != 1:
        raise RuntimeError(f"probe failure auth anchor={s.count(failure_anchor)}")
    s = s.replace(failure_anchor, failure_new, 1)

    http_anchor = '''                "status": exc.response.status_code,
                "detail": self._redact(exc.response.text[:500]),
'''
    http_new = '''                "status": exc.response.status_code,
                "detail": self._redact(exc.response.text[:500]),
                "authenticated": False if exc.response.status_code in {400, 401} else None,
'''
    if s.count(http_anchor) != 1:
        raise RuntimeError(f"probe HTTP auth anchor={s.count(http_anchor)}")
    s = s.replace(http_anchor, http_new, 1)

    exc_anchor = '''                "status": "ERROR",
                "detail": self._redact(f"{type(exc).__name__}: {exc}"),
'''
    exc_new = '''                "status": "ERROR",
                "detail": self._redact(f"{type(exc).__name__}: {exc}"),
                "authenticated": None,
'''
    if s.count(exc_anchor) != 1:
        raise RuntimeError(f"probe exception auth anchor={s.count(exc_anchor)}")
    s = s.replace(exc_anchor, exc_new, 1)
    p.write_text(s, encoding="utf-8")


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    init_anchor = '''        self._provider_revalidation_interval_seconds = 300.0
        self.loop = asyncio.new_event_loop()
'''
    init_new = '''        self._provider_revalidation_interval_seconds = 300.0
        # DEV310 validation ownership. Provider probes are asynchronous, so an old
        # startup/revalidation result must never overwrite a newer manual key.
        self._provider_validation_epoch = 0
        self._provider_validation_source = "none"
        self._provider_validation_lock = threading.Lock()
        self.loop = asyncio.new_event_loop()
'''
    if s.count(init_anchor) != 1:
        raise RuntimeError(f"provider init anchor={s.count(init_anchor)}")
    s = s.replace(init_anchor, init_new, 1)

    method_anchor = '''    def start_provider_validation_background(self) -> bool:
        """Validate a recovered/pasted startup key without delaying core health."""
'''
    method_new = '''    def _begin_provider_validation(self, source: str) -> int:
        with self._provider_validation_lock:
            self._provider_validation_epoch += 1
            self._provider_validation_source = str(source or "unknown")
            return int(self._provider_validation_epoch)

    def _provider_validation_is_current(self, epoch: int) -> bool:
        with self._provider_validation_lock:
            return int(epoch) == int(self._provider_validation_epoch)

    def start_provider_validation_background(self) -> bool:
        """Validate a recovered startup key without allowing stale-result overwrite."""
'''
    if s.count(method_anchor) != 1:
        raise RuntimeError(f"validation helper anchor={s.count(method_anchor)}")
    s = s.replace(method_anchor, method_new, 1)

    startup_old = '''        key = self._pending_gemini_key
        self._pending_gemini_key = None
        self.provider_validation_in_progress = True
        def _runner():
            try:
                self.call(self.activate_gemini(key), timeout=90)
'''
    startup_new = '''        key = self._pending_gemini_key
        self._pending_gemini_key = None
        epoch = self._begin_provider_validation("startup")
        self.provider_validation_in_progress = True
        def _runner():
            try:
                self.call(
                    self.activate_gemini(
                        key, validation_epoch=epoch, validation_source="startup"
                    ),
                    timeout=90,
                )
'''
    if s.count(startup_old) != 1:
        raise RuntimeError(f"startup validation anchor={s.count(startup_old)}")
    s = s.replace(startup_old, startup_new, 1)

    reval_old = '''        self._next_provider_revalidation_ts = now + float(self._provider_revalidation_interval_seconds)
        self.provider_validation_in_progress = True

        def _runner():
            try:
                self.call(self.revalidate_stored_gemini(), timeout=90)
'''
    reval_new = '''        self._next_provider_revalidation_ts = now + float(self._provider_revalidation_interval_seconds)
        epoch = self._begin_provider_validation("auto_revalidation")
        self.provider_validation_in_progress = True

        def _runner():
            try:
                self.call(
                    self.revalidate_stored_gemini(
                        validation_epoch=epoch, validation_source="auto_revalidation"
                    ),
                    timeout=90,
                )
'''
    if s.count(reval_old) != 1:
        raise RuntimeError(f"stored revalidation anchor={s.count(reval_old)}")
    s = s.replace(reval_old, reval_new, 1)

    start = s.index("    async def activate_gemini(self, raw_key: str):")
    end = s.index("    async def _ensure_scheduler_health(self):", start)
    old_block = s[start:end]
    new_block = '''    async def activate_gemini(
        self,
        raw_key: str,
        *,
        validation_epoch: int | None = None,
        validation_source: str = "manual",
    ):
        # Candidate validation is transactional: until the candidate is
        # authenticated, the currently-good provider state remains untouched.
        if validation_epoch is None:
            validation_epoch = self._begin_provider_validation(validation_source)
            if validation_source == "manual":
                # A new explicit key supersedes any startup key still in flight.
                self._pending_gemini_key = None

        key = _normalize_gemini_key(raw_key)
        if not key:
            candidate = str(raw_key or "").strip().strip("\\\"'").strip()
            if 20 <= len(candidate) <= 256 and not any(ch.isspace() for ch in candidate):
                key = candidate
        if not key:
            raise ValueError("No se reconoció una API key válida. Revisa que hayas pegado la clave completa.")

        transport = self.GeminiInteractionsTransport(api_key=key, model="auto")
        probe = await transport.probe_live()

        # Last-validation-wins. A slower startup/old-key probe is read-only once a
        # newer validation has begun.
        if not self._provider_validation_is_current(validation_epoch):
            snap = await self.snapshot()
            snap["provider_validation_superseded"] = True
            return snap

        if not probe.get("ok"):
            detail = str(probe.get("detail") or probe.get("status") or "validación fallida")
            detail = detail.replace(key, "<redacted-api-key>")[:900]
            status = str(probe.get("status") or "GENERATION_UNAVAILABLE")
            status_upper = status.upper()
            models_visible = int(probe.get("models_visible") or 0)
            authenticated = probe.get("authenticated")
            recognized = bool(authenticated is True or models_visible > 0)
            hard_rejected = status_upper in {
                "401", "UNAUTHENTICATED", "API_KEY_INVALID", "INVALID_API_KEY"
            }

            if not recognized:
                # Do not let an invalid/unverifiable replacement disable a working
                # credential. Only expose candidate failure diagnostics.
                self.gemini_validation_error = f"{status}: {detail}"[:900]
                if not self.gemini_key_recognized and not self.gemini_key:
                    self.gemini_key_status = status
                    self.provider_mode = (
                        "gemini-validation-failed"
                        if hard_rejected else "gemini-validation-deferred"
                    )
                if hard_rejected:
                    raise RuntimeError(f"Google rechazó la clave Gemini: {detail}")
                raise RuntimeError(
                    "No se pudo comprobar la clave Gemini ahora; la credencial anterior "
                    f"se mantiene intacta. Detalle: {detail}"
                )

            # Google authenticated the key, but generation is temporarily
            # unavailable (quota/model/network at generation stage). Persist the
            # credential and wait autonomously instead of telling the user to
            # create another key.
            saved = _save_windows_dpapi_gemini_key(key)
            self.gemini_key = key
            self.gemini_key_recognized = True
            self.gemini_key_status = status
            self.gemini_validation_error = f"{status}: {detail}"[:900]
            self.execution_enabled = False
            self.gemini_model = str(probe.get("model") or "") or None
            self.provider_mode = "gemini-authenticated-waiting"
            self._next_provider_revalidation_ts = (
                time.time() + float(self._provider_revalidation_interval_seconds)
            )

            state = self._state_obj()
            if state is not None:
                state.metadata["gemini_dpapi_saved"] = bool(saved)
                state.metadata["gemini_key_recognized"] = True
                state.metadata["gemini_key_status"] = status
                state.metadata["provider_mode"] = self.provider_mode
                state.metadata["gemini_live_verified"] = False
                state.metadata["execution_disabled_reason"] = self.gemini_validation_error
                state.metadata["provider_wait_v1"] = {
                    "active": True,
                    "category": "quota" if "QUOTA" in status_upper else "provider_unavailable",
                    "provider": "gemini-interactions",
                    "retry_after_seconds": int(self._provider_revalidation_interval_seconds),
                    "retry_after_ts": self._next_provider_revalidation_ts,
                    "reason": self.gemini_validation_error,
                    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "recoveries_consumed": 0,
                    "credential_authenticated": True,
                    "automatic_retry": True,
                }
                store = self.projects.store(state.id)
                store.save(state)
                self.projects.touch(state)
                self.router = self._router()
                if self.scheduler is not None:
                    self.scheduler.router = self.router
                    self.scheduler.graph.refresh(state)
            return await self.snapshot()

        # Commit successful validation only if it is still the newest one.
        if not self._provider_validation_is_current(validation_epoch):
            snap = await self.snapshot()
            snap["provider_validation_superseded"] = True
            return snap

        dpapi_saved = _save_windows_dpapi_gemini_key(key)
        self.gemini_key = key
        self.gemini_validation_error = None
        self.gemini_key_recognized = True
        self.gemini_key_status = "LIVE_VERIFIED"
        self.execution_enabled = True
        self.gemini_model = str(probe.get("model") or "") or None
        self.provider_mode = "gemini-live-verified"
        self._next_provider_revalidation_ts = 0.0

        state = self._state_obj()
        if state is not None:
            state.metadata["gemini_dpapi_saved"] = bool(dpapi_saved)
            state.metadata["gemini_key_recognized"] = True
            state.metadata["gemini_key_status"] = "LIVE_VERIFIED"
            state.metadata["provider_mode"] = self.provider_mode
            state.metadata["gemini_live_verified"] = True
            if self.gemini_model:
                state.metadata["gemini_model"] = self.gemini_model
            state.metadata.pop("execution_disabled_reason", None)
            state.metadata.pop("provider_wait_v1", None)
            from ceo_core.models import TaskStatus
            for waiting_task in state.leaf_tasks:
                if waiting_task.metadata.pop("waiting_provider_v1", None) is not None:
                    waiting_task.metadata.pop("retry_after_ts", None)
                    if waiting_task.status == TaskStatus.BLOCKED:
                        waiting_task.status = TaskStatus.WAITING
            state.paused = False
            store = self.projects.store(state.id)
            store.save(state)
            self.projects.touch(state)
            self.router = self._router()
            if self.scheduler is None and not state.completed_at and not state.cancelled_at and not state.metadata.get("operator_cancelled"):
                self.scheduler = self.ContinuousScheduler(
                    state, None, store, graph=self.Graph(), router=self.router
                )
                self.scheduler.start()
            elif self.scheduler is not None:
                self.scheduler.router = self.router
                self.scheduler.graph.refresh(state)
        return await self.snapshot()

    async def revalidate_stored_gemini(
        self,
        *,
        validation_epoch: int | None = None,
        validation_source: str = "manual_revalidate",
    ):
        key = _load_windows_dpapi_gemini_key()
        if not key:
            raise RuntimeError("No hay una clave Gemini cifrada guardada para este usuario de Windows.")
        try:
            return await self.activate_gemini(
                key,
                validation_epoch=validation_epoch,
                validation_source=validation_source,
            )
        except Exception as exc:
            # Candidate/revalidation diagnostics may change, but a failed
            # revalidation never erases a previously-good runtime credential.
            self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
            if not self.gemini_key_recognized:
                self.provider_mode = "gemini-validation-failed"
            raise
        finally:
            key = None

'''
    s = s[:start] + new_block + s[end:]

    # UI truthfulness: authenticated waiting is not "NO active", and the manual
    # revalidate button must not claim success merely because HTTP returned 200.
    old_ui = """$('provider').textContent=(live?'IA conectada':(keyRecognized?'Clave Gemini reconocida · IA bloqueada':'IA no activa'))+(schedulerAlive?' · motor activo':' · motor detenido');
$('execPill').textContent=live?'✓ Gemini VALIDADO y activo':(keyRecognized?'⚠ Gemini reconocido · sin ejecución':'⚠ Gemini NO activo');$('execPill').className='pill '+(live?'live':'warn');$('keyBox').style.display=live?'none':'flex';
const geminiFailed=!live&&s.provider_mode==='gemini-validation-failed';const geminiErr=String(s.gemini_validation_error||'').slice(0,620);
$('geminiDetail').textContent=live?('Conexión Gemini verificada'+(s.gemini_model?' · modelo '+s.gemini_model:'')+'.'):(keyRecognized?('✓ Nueva clave reconocida por Google, pero la ejecución está bloqueada ('+(keyStatus||'sin detalle')+'). '+(geminiErr||'Pulsa “Reintentar guardada” cuando haya cuota disponible.')):(geminiFailed?('Clave rechazada o no autenticada. '+geminiErr):('Sin validación Gemini. CEO no ejecutará trabajo IA.')));
"""
    new_ui = """$('provider').textContent=(live?'IA conectada':(keyRecognized?'Clave Gemini autenticada · proveedor en espera':'IA no activa'))+(schedulerAlive?' · motor activo':' · motor detenido');
$('execPill').textContent=live?'✓ Gemini VALIDADO y activo':(keyRecognized?'⏳ Gemini autenticado · EN ESPERA':'⚠ Gemini NO activo');$('execPill').className='pill '+(live?'live':'warn');$('keyBox').style.display=live?'none':'flex';
const geminiFailed=!live&&s.provider_mode==='gemini-validation-failed';const geminiErr=String(s.gemini_validation_error||'').slice(0,620);
$('geminiDetail').textContent=live?('Conexión Gemini verificada'+(s.gemini_model?' · modelo '+s.gemini_model:'')+'.'):(keyRecognized?('✓ Clave autenticada y guardada. Google no permite generar ahora ('+(keyStatus||'disponibilidad temporal')+'). CEO reintentará automáticamente; no necesitas crear otra clave. '+geminiErr):(geminiFailed?('Clave rechazada o no autenticada. '+geminiErr):('Sin validación Gemini. CEO no ejecutará trabajo IA.')));
"""
    if s.count(old_ui) != 1:
        raise RuntimeError(f"provider UI anchor={s.count(old_ui)}")
    s = s.replace(old_ui, new_ui, 1)

    old_retry = """async function retryStoredGemini(){try{$('geminiDetail').textContent='Reintentando la clave cifrada guardada…';const s=await j('/api/session-key/revalidate',{method:'POST'});render(s);$('geminiDetail').textContent='✓ Gemini validado y activo'+(s.gemini_model?' · '+s.gemini_model:'')+'.'}catch(e){$('geminiDetail').textContent='✗ Reintento Gemini fallido: '+e.message;$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
"""
    new_retry = """async function retryStoredGemini(){try{$('geminiDetail').textContent='Reintentando la clave cifrada guardada…';const s=await j('/api/session-key/revalidate',{method:'POST'});render(s);if(s.execution_enabled){$('geminiDetail').textContent='✓ Gemini validado y activo'+(s.gemini_model?' · '+s.gemini_model:'')+'.'}else if(s.gemini_key_recognized){$('geminiDetail').textContent='✓ Clave autenticada. Proveedor temporalmente en espera; CEO reintentará solo.'}else{$('geminiDetail').textContent='✗ La clave guardada no pudo autenticarse.'}}catch(e){$('geminiDetail').textContent='✗ Reintento Gemini fallido: '+e.message;$('diag').innerHTML='<div class="error">'+esc(e.message)+'</div>'}}
"""
    if s.count(old_retry) != 1:
        raise RuntimeError(f"retry UI anchor={s.count(old_retry)}")
    s = s.replace(old_retry, new_retry, 1)

    p.write_text(s, encoding="utf-8")


def update_contract() -> None:
    # Version identity is surfaced through the stdlib app and installer.
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        p = ROOT / rel
        if p.is_file():
            p.write_text(p.read_text(encoding="utf-8").replace(OLD_VERSION, VERSION), encoding="utf-8")

    cpath = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(cpath.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in hashes:
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

    patch_gemini_transport()
    patch_work_mode()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "invariants": [
            "newest_provider_validation_owns_state",
            "failed_candidate_cannot_disable_working_key",
            "authenticated_generation_outage_is_wait_not_invalid_key",
            "stored_key_retries_are_automatic_and_truthful",
            "probe_generation_budget_is_bounded",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
