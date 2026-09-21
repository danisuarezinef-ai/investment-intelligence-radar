from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.86-rc1-provider-session-integrity.zip"
ROOT = pathlib.Path(os.environ.get("CEO_DEV311_BUILD_ROOT", "/tmp/ceo-dev311-update-shell"))
OLD_VERSION = "1.5.86-rc1-provider-session-integrity"
VERSION = "1.5.87-rc1-update-shell-integrity"


def patch_work_mode() -> None:
    p = ROOT / "scripts" / "ceo_stdlib_work_mode.py"
    s = p.read_text(encoding="utf-8")

    old_vars = """let updateState=null;
function toggleUpdateInfo(){const x=$('updateInfo');x.style.display=x.style.display==='none'?'block':'none'}
"""
    new_vars = """let updateState=null;let updateActionBusy=false;
function toggleUpdateInfo(){const x=$('updateInfo');x.style.display=x.style.display==='none'?'block':'none'}
"""
    if s.count(old_vars) != 1:
        raise RuntimeError(f"update busy vars anchor={s.count(old_vars)}")
    s = s.replace(old_vars, new_vars, 1)

    old_poll = """async function pollUpdateProgress(){try{const p=await j('/api/update/progress');const phase=String(p.phase||'').toLowerCase();const labels={downloading:'Descargando',downloaded:'Descarga completa',verifying:'Verificando firma e integridad',extracting:'Preparando versión',ready_to_install:'Lista para instalar',preflight:'Probando nueva versión sin activarla',preflight_ok:'Prueba previa superada',activating:'Activando',waiting_old_process:'Cerrando versión anterior',launching_new_version:'Arrancando nueva versión',health_check:'Comprobando salud',healthy:'Actualización completada',rollback:'Revirtiendo',rolled_back:'Versión anterior restaurada'};let percent=Number(p.percent);if(!Number.isFinite(percent)){percent=phase==='verifying'?78:phase==='extracting'?86:phase==='ready_to_install'?100:0}let detail='';if(p.bytes_expected>0)detail='Descargados '+Math.round((p.bytes_downloaded||0)/1024)+' KB de '+Math.round(p.bytes_expected/1024)+' KB';showUpdateProgress(percent,labels[phase]||phase||'Procesando',detail)}catch(e){}}
"""
    new_poll = """async function pollUpdateProgress(){try{const p=await j('/api/update/progress');const phase=String(p.phase||'').toLowerCase();const labels={downloading:'Descargando',downloaded:'Descarga completa',verifying:'Verificando firma e integridad',extracting:'Preparando versión',ready_to_install:'Lista para instalar',preflight:'Probando nueva versión sin activarla',preflight_ok:'Prueba previa superada',activating:'Activando',waiting_old_process:'Cerrando versión anterior',launching_new_version:'Arrancando nueva versión',health_check:'Comprobando salud',healthy:'Actualización completada',rollback:'Revirtiendo',rolled_back:'Versión anterior restaurada'};let percent=Number(p.percent);if(!Number.isFinite(percent)){percent=phase==='verifying'?78:phase==='extracting'?86:phase==='ready_to_install'?100:0}let detail='';if(p.bytes_expected>0)detail='Descargados '+Math.round((p.bytes_downloaded||0)/1024)+' KB de '+Math.round(p.bytes_expected/1024)+' KB';showUpdateProgress(percent,labels[phase]||phase||'Procesando',detail);if(phase==='ready_to_install'&&!updateActionBusy){stopUpdateProgress();$('updateHeadline').textContent='Actualización lista para instalar';$('updateDetail').textContent='Descarga, firma e integridad verificadas.';setUpdateButton('Instalar y reiniciar',true,String(p.version||''))}}catch(e){}}
"""
    if s.count(old_poll) != 1:
        raise RuntimeError(f"update progress anchor={s.count(old_poll)}")
    s = s.replace(old_poll, new_poll, 1)

    old_click_start = """async function oneClickUpdate(){const b=$('oneClickUpdateBtn');if(!updateState||(!updateState.available&&!(updateState.staged||[]).some(x=>!x.installed&&!x.rolled_back))){return checkUpdate()}try{let installable="""
    new_click_start = """async function oneClickUpdate(){if(updateActionBusy)return;const b=$('oneClickUpdateBtn');if(!updateState||(!updateState.available&&!(updateState.staged||[]).some(x=>!x.installed&&!x.rolled_back))){return checkUpdate()}updateActionBusy=true;try{let installable="""
    if s.count(old_click_start) != 1:
        raise RuntimeError(f"oneClick start anchor={s.count(old_click_start)}")
    s = s.replace(old_click_start, new_click_start, 1)

    old_stage_tail = """const r=await j('/api/update/stage',{method:'POST'});if(r.available===false){stopUpdateProgress();return await updateStatus(true)}stopUpdateProgress();showUpdateProgress(100,'Lista para instalar','Descarga y verificaciones completadas.');await updateStatus(false);installable=(updateState?.staged||[]).find(x=>!x.installed&&!x.rolled_back&&!x.preflight_failed)}if(!installable)throw new Error('La actualización no quedó preparada para instalar.');"""
    new_stage_tail = """const r=await j('/api/update/stage',{method:'POST'});if(r.available===false){stopUpdateProgress();updateActionBusy=false;return await updateStatus(true)}stopUpdateProgress();showUpdateProgress(100,'Lista para instalar','Descarga y verificaciones completadas.');installable=(r&&r.receipt&&!r.receipt.installed&&!r.receipt.rolled_back&&!r.receipt.preflight_failed)?r.receipt:null;if(installable){updateState=updateState||{};updateState.staged=[installable,...((updateState.staged||[]).filter(x=>String(x.version||'')!==String(installable.version||'')))];$('updateHeadline').textContent='Actualización lista para instalar';$('updateDetail').textContent=installable.version+' ya está descargada y verificada.';setUpdateButton('Instalar y reiniciar',true,installable.version)}else{const refreshed=await updateStatus(false);installable=(refreshed?.staged||[]).find(x=>!x.installed&&!x.rolled_back&&!x.preflight_failed)}}if(!installable)throw new Error('La actualización no quedó preparada para instalar.');"""
    if s.count(old_stage_tail) != 1:
        raise RuntimeError(f"stage tail anchor={s.count(old_stage_tail)}")
    s = s.replace(old_stage_tail, new_stage_tail, 1)

    old_cancel = """if(!ok){$('updateHeadline').textContent='Actualización preparada';$('updateDetail').textContent='Queda lista. Puedes instalarla cuando quieras con el mismo botón.';setUpdateButton('Instalar y reiniciar',true,version);return}"""
    new_cancel = """if(!ok){updateActionBusy=false;$('updateHeadline').textContent='Actualización preparada';$('updateDetail').textContent='Queda lista. Puedes instalarla cuando quieras con el mismo botón.';setUpdateButton('Instalar y reiniciar',true,version);return}"""
    if s.count(old_cancel) != 1:
        raise RuntimeError(f"cancel install anchor={s.count(old_cancel)}")
    s = s.replace(old_cancel, new_cancel, 1)

    old_end = """waitForRestart(version)}catch(e){stopUpdateProgress();const msg=e.message;await updateStatus(false);$('updateHeadline').textContent='No se pudo actualizar';$('updateDetail').textContent=msg;setUpdateButton('Reintentar actualización',true)}}
"""
    new_end = """waitForRestart(version)}catch(e){stopUpdateProgress();const msg=e.message;await updateStatus(false);$('updateHeadline').textContent='No se pudo actualizar';$('updateDetail').textContent=msg;setUpdateButton('Reintentar actualización',true)}finally{updateActionBusy=false}}
"""
    if s.count(old_end) != 1:
        raise RuntimeError(f"oneClick finally anchor={s.count(old_end)}")
    s = s.replace(old_end, new_end, 1)

    p.write_text(s, encoding="utf-8")


def patch_launcher() -> None:
    p = ROOT / "scripts" / "launch_current.py"
    s = p.read_text(encoding="utf-8")

    import_anchor = """import traceback
from pathlib import Path
"""
    import_new = """import traceback
import urllib.request
import webbrowser
from pathlib import Path
"""
    if s.count(import_anchor) != 1:
        raise RuntimeError(f"launcher imports anchor={s.count(import_anchor)}")
    s = s.replace(import_anchor, import_new, 1)

    helper_anchor = """def _write_status(payload: dict) -> None:
"""
    helper_new = """def _probe_existing_ceo() -> str | None:
    for port in range(8765, 8781):
        url = f"http://127.0.0.1:{port}"
        try:
            req = urllib.request.Request(url + "/api/health", headers={"User-Agent": "CEO-de-IAs-Launcher/1"})
            with urllib.request.urlopen(req, timeout=0.45) as resp:
                raw = resp.read(512 * 1024)
            row = json.loads(raw.decode("utf-8"))
            if isinstance(row, dict) and row.get("ok") is True and str(row.get("version") or "").strip():
                return url
        except Exception:
            continue
    return None


def _open_existing_as_app(url: str) -> str:
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        ]
        for exe in candidates:
            try:
                if exe.is_file():
                    subprocess.Popen(
                        [str(exe), f"--app={url}", "--start-maximized"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    return str(exe)
            except Exception:
                pass
    webbrowser.open(url, new=1)
    return "default-browser"


def _write_status(payload: dict) -> None:
"""
    if s.count(helper_anchor) != 1:
        raise RuntimeError(f"launcher helper anchor={s.count(helper_anchor)}")
    s = s.replace(helper_anchor, helper_new, 1)

    main_anchor = """def main() -> int:
    try:
        # Heal stale .part/extraction directories and a cut-over that never
"""
    main_new = """def main() -> int:
    try:
        # Normal shortcut behavior is single-instance: if CEO is already healthy,
        # open/focus that backend in an app-style browser window instead of
        # starting a second scheduler on another localhost port.
        existing = _probe_existing_ceo()
        if existing:
            browser = _open_existing_as_app(existing)
            _write_status({
                "status": "EXISTING_INSTANCE_OPENED",
                "url": existing,
                "browser": browser,
                "single_instance": True,
            })
            return 0

        # Heal stale .part/extraction directories and a cut-over that never
"""
    if s.count(main_anchor) != 1:
        raise RuntimeError(f"launcher main anchor={s.count(main_anchor)}")
    s = s.replace(main_anchor, main_new, 1)
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
    patch_launcher()
    update_contract()

    print(json.dumps({
        "ok": True,
        "base": OLD_VERSION,
        "version": VERSION,
        "root": str(ROOT),
        "invariants": [
            "stage_receipt_drives_ready_to_install_without_second_status_roundtrip",
            "ready_to_install_telemetry_can_self_heal_button_state",
            "update_action_is_single_flight",
            "desktop_shortcut_reuses_existing_healthy_backend",
            "existing_backend_opens_in_browser_app_mode",
            "human_install_confirmation_preserved",
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
