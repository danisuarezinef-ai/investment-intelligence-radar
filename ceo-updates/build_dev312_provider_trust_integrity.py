from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.87-rc1-update-shell-integrity.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV312_BUILD_ROOT", "/tmp/ceo-dev312-provider-trust"))
OLD_VERSION = "1.5.87-rc1-update-shell-integrity"
VERSION = "1.5.88-rc1-provider-trust-integrity"


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    # Persist authenticated-key trust metadata with DPAPI as well; no plaintext
    # credential or plaintext fingerprint is written to disk.
    trust_anchor = '''def _gemini_secret_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CEO de IAs" / "secrets" / "gemini_api_key.dpapi"


'''
    trust_new = '''def _gemini_secret_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CEO de IAs" / "secrets" / "gemini_api_key.dpapi"


def _gemini_trust_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "CEO de IAs" / "secrets" / "gemini_auth_trust.dpapi"


def _gemini_key_fingerprint(key: str) -> str:
    import hashlib
    return hashlib.sha256(str(key or "").encode("utf-8")).hexdigest()


'''
    if s.count(trust_anchor) != 1:
        raise RuntimeError(f"trust path anchor={s.count(trust_anchor)}")
    s = s.replace(trust_anchor, trust_new, 1)

    # Insert trust save/load helpers after existing DPAPI key load/save helpers.
    helper_anchor = '''def _forget_windows_dpapi_gemini_key() -> bool:
'''
    idx = s.index(helper_anchor)
    trust_helpers = '''def _save_windows_dpapi_gemini_trust(key: str, *, model: str | None = None, source: str = "verified") -> bool:
    if sys.platform != "win32" or not key:
        return False
    payload = json.dumps({
        "schema": 1,
        "fingerprint": _gemini_key_fingerprint(key),
        "model": str(model or ""),
        "source": str(source or "verified"),
        "verified_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }, ensure_ascii=False, sort_keys=True)
    blob = _windows_dpapi_protect_text(payload)
    if not blob:
        return False
    path = _gemini_trust_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(blob)
    tmp.replace(path)
    return True


def _load_windows_dpapi_gemini_trust(key: str) -> dict:
    if sys.platform != "win32" or not key:
        return {}
    path = _gemini_trust_path()
    try:
        if not path.is_file():
            return {}
        raw = _windows_dpapi_unprotect_text(path.read_bytes())
        if not raw:
            return {}
        row = json.loads(raw)
        if not isinstance(row, dict):
            return {}
        if str(row.get("fingerprint") or "") != _gemini_key_fingerprint(key):
            return {}
        return row
    except Exception:
        return {}


def _forget_windows_dpapi_gemini_trust() -> bool:
    path = _gemini_trust_path()
    try:
        if path.exists():
            path.unlink()
        return True
    except Exception:
        return False


'''
    s = s[:idx] + trust_helpers + s[idx:]

    # Forgetting a key must forget its trust marker too.
    forget_anchor = '''def _forget_windows_dpapi_gemini_key() -> bool:
    try:
        path = _gemini_secret_path()
'''
    forget_new = '''def _forget_windows_dpapi_gemini_key() -> bool:
    _forget_windows_dpapi_gemini_trust()
    try:
        path = _gemini_secret_path()
'''
    if s.count(forget_anchor) != 1:
        raise RuntimeError(f"forget trust anchor={s.count(forget_anchor)}")
    s = s.replace(forget_anchor, forget_new, 1)

    # At startup, if the exact DPAPI key has prior authenticated trust, preserve
    # recognition across transport outages while still requiring live generation
    # before execution_enabled becomes true.
    init_anchor = '''        self._pending_gemini_key = (gemini_key or "").strip() or None
        self.gemini_key = None
        self.execution_enabled = False
        self.provider_mode = "gemini-key-pending-validation" if self._pending_gemini_key else "plan-only (sin Gemini)"
        self.gemini_model = None
        self.gemini_validation_error = None
        self.gemini_key_recognized = False
        self.gemini_key_status = None
'''
    init_new = '''        self._pending_gemini_key = (gemini_key or "").strip() or None
        startup_trust = _load_windows_dpapi_gemini_trust(self._pending_gemini_key) if self._pending_gemini_key else {}
        self.gemini_key = self._pending_gemini_key if startup_trust else None
        self.execution_enabled = False
        self.provider_mode = (
            "gemini-authenticated-waiting"
            if startup_trust
            else ("gemini-key-pending-validation" if self._pending_gemini_key else "plan-only (sin Gemini)")
        )
        self.gemini_model = str(startup_trust.get("model") or "") or None
        self.gemini_validation_error = None
        self.gemini_key_recognized = bool(startup_trust)
        self.gemini_key_status = "TRUSTED_PREVIOUSLY_VERIFIED" if startup_trust else None
'''
    if s.count(init_anchor) != 1:
        raise RuntimeError(f"startup trust anchor={s.count(init_anchor)}")
    s = s.replace(init_anchor, init_new, 1)

    # Startup validation catch must not demote an already trusted key merely
    # because the network probe failed.
    catch_anchor = '''            except Exception as exc:
                self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
                self.provider_mode = "gemini-validation-failed"
            finally:
'''
    catch_new = '''            except Exception as exc:
                self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
                if self.gemini_key_recognized:
                    self.provider_mode = "gemini-authenticated-waiting"
                    self.gemini_key_status = self.gemini_key_status or "TRANSPORT_UNAVAILABLE"
                else:
                    self.provider_mode = "gemini-validation-deferred"
            finally:
'''
    if s.count(catch_anchor) != 1:
        raise RuntimeError(f"startup catch anchor={s.count(catch_anchor)}")
    s = s.replace(catch_anchor, catch_new, 1)

    # A transport-unknown probe can reuse prior trust for the exact same key.
    recognized_anchor = '''            authenticated = probe.get("authenticated")
            recognized = bool(authenticated is True or models_visible > 0)
            hard_rejected = status_upper in {
'''
    recognized_new = '''            authenticated = probe.get("authenticated")
            prior_trust = _load_windows_dpapi_gemini_trust(key)
            recognized = bool(authenticated is True or models_visible > 0 or prior_trust)
            hard_rejected = status_upper in {
'''
    if s.count(recognized_anchor) != 1:
        raise RuntimeError(f"prior trust recognize anchor={s.count(recognized_anchor)}")
    s = s.replace(recognized_anchor, recognized_new, 1)

    # Explicit credential rejection is authoritative and revokes trust; transport
    # errors never do.
    reject_anchor = '''                if hard_rejected:
                    raise RuntimeError(f"Google rechazó la clave Gemini: {detail}")
'''
    reject_new = '''                if hard_rejected:
                    _forget_windows_dpapi_gemini_trust()
                    if self.gemini_key == key:
                        self.gemini_key = None
                    self.gemini_key_recognized = False
                    self.execution_enabled = False
                    self.gemini_key_status = status
                    self.provider_mode = "gemini-validation-failed"
                    raise RuntimeError(f"Google rechazó la clave Gemini: {detail}")
'''
    if s.count(reject_anchor) != 1:
        raise RuntimeError(f"hard reject anchor={s.count(reject_anchor)}")
    s = s.replace(reject_anchor, reject_new, 1)

    # Any authenticated probe result refreshes encrypted trust.
    waiting_save_anchor = '''            saved = _save_windows_dpapi_gemini_key(key)
            self.gemini_key = key
'''
    waiting_save_new = '''            saved = _save_windows_dpapi_gemini_key(key)
            trust_saved = _save_windows_dpapi_gemini_trust(
                key,
                model=str(probe.get("model") or "") or self.gemini_model,
                source="authenticated_wait",
            )
            self.gemini_key = key
'''
    if s.count(waiting_save_anchor) != 1:
        raise RuntimeError(f"waiting trust save anchor={s.count(waiting_save_anchor)}")
    s = s.replace(waiting_save_anchor, waiting_save_new, 1)

    waiting_meta_anchor = '''                state.metadata["gemini_dpapi_saved"] = bool(saved)
                state.metadata["gemini_key_recognized"] = True
'''
    waiting_meta_new = '''                state.metadata["gemini_dpapi_saved"] = bool(saved)
                state.metadata["gemini_auth_trust_saved"] = bool(trust_saved)
                state.metadata["gemini_key_recognized"] = True
'''
    if s.count(waiting_meta_anchor) < 1:
        raise RuntimeError("waiting trust metadata anchor missing")
    s = s.replace(waiting_meta_anchor, waiting_meta_new, 1)

    live_save_anchor = '''        dpapi_saved = _save_windows_dpapi_gemini_key(key)
        self.gemini_key = key
'''
    live_save_new = '''        dpapi_saved = _save_windows_dpapi_gemini_key(key)
        trust_saved = _save_windows_dpapi_gemini_trust(
            key,
            model=str(probe.get("model") or "") or self.gemini_model,
            source="live_verified",
        )
        self.gemini_key = key
'''
    if s.count(live_save_anchor) != 1:
        raise RuntimeError(f"live trust save anchor={s.count(live_save_anchor)}")
    s = s.replace(live_save_anchor, live_save_new, 1)

    live_meta_anchor = '''            state.metadata["gemini_dpapi_saved"] = bool(dpapi_saved)
            state.metadata["gemini_key_recognized"] = True
'''
    live_meta_new = '''            state.metadata["gemini_dpapi_saved"] = bool(dpapi_saved)
            state.metadata["gemini_auth_trust_saved"] = bool(trust_saved)
            state.metadata["gemini_key_recognized"] = True
'''
    if s.count(live_meta_anchor) != 1:
        raise RuntimeError(f"live trust metadata anchor={s.count(live_meta_anchor)}")
    s = s.replace(live_meta_anchor, live_meta_new, 1)

    # Revalidation catch must preserve authenticated-waiting for trusted key.
    reval_anchor = '''            self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
            if not self.gemini_key_recognized:
                self.provider_mode = "gemini-validation-failed"
            raise
'''
    reval_new = '''            self.gemini_validation_error = f"{type(exc).__name__}: {exc}"[:900]
            if self.gemini_key_recognized:
                self.provider_mode = "gemini-authenticated-waiting"
                self.gemini_key_status = self.gemini_key_status or "TRANSPORT_UNAVAILABLE"
            else:
                self.provider_mode = "gemini-validation-deferred"
            raise
'''
    if s.count(reval_anchor) != 1:
        raise RuntimeError(f"revalidation catch anchor={s.count(reval_anchor)}")
    s = s.replace(reval_anchor, reval_new, 1)

    # Make UI distinguish transport failure from credential rejection.
    ui_anchor = """$('geminiDetail').textContent=live?('Conexión Gemini verificada'+(s.gemini_model?' · modelo '+s.gemini_model:'')+'.'):(keyRecognized?('✓ Clave autenticada y guardada. Google no permite generar ahora ('+(keyStatus||'disponibilidad temporal')+'). CEO reintentará automáticamente; no necesitas crear otra clave. '+geminiErr):(geminiFailed?('Clave rechazada o no autenticada. '+geminiErr):('Sin validación Gemini. CEO no ejecutará trabajo IA.')));
"""
    ui_new = """const transportProblem=/ConnectError|Timeout|NETWORK|TRANSPORT|UNAVAILABLE/i.test(geminiErr+' '+keyStatus);$('geminiDetail').textContent=live?('Conexión Gemini verificada'+(s.gemini_model?' · modelo '+s.gemini_model:'')+'.'):(keyRecognized?('✓ Clave autenticada y guardada. '+(transportProblem?'Conexión con Gemini temporalmente no disponible.':'Gemini no permite generar ahora.')+' CEO reintentará automáticamente; no necesitas crear otra clave. '+geminiErr):(geminiFailed?('Clave rechazada o no autenticada. '+geminiErr):('No se pudo verificar Gemini en este momento. CEO conserva la clave cifrada y reintentará.')));
"""
    if s.count(ui_anchor) != 1:
        raise RuntimeError(f"truthful auth UI anchor={s.count(ui_anchor)}")
    s = s.replace(ui_anchor, ui_new, 1)

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

    patch_work_mode()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "invariants": [
            "authenticated_key_trust_persists_encrypted_across_restart",
            "transport_failure_never_demotes_prior_authenticated_key",
            "only_explicit_auth_rejection_revokes_trust",
            "startup_probe_cannot_false-label_transport_as_auth_failure",
            "dev311_update_shell_fixes_inherited",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
