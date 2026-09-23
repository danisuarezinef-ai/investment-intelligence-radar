from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
BASE=REPO/"ceo-updates"/"CEO_1.5.89-rc1-native-transport-integrity.zip"
SRC=REPO/"ceo-browser"
CORE_SRC=REPO/"ceo-updates"/"dev313-inspect-routing"
SOURCE_SHA=(os.environ.get("GITHUB_SHA") or "local").strip()
BUILD_ID=(SOURCE_SHA[:8] if SOURCE_SHA and SOURCE_SHA!="local" else "local")
OUT=SRC/f"CEO_FIRST_TRIAL_LAB_{BUILD_ID}.zip"
ROOT=Path(os.environ.get("CEO_FIRST_TRIAL_BUILD_ROOT", str(REPO/".tmp-first-trial-lab")))

BROWSER_FILES=[
    "windows_chatgpt_cdp_driver.ps1",
    "open_chatgpt_profile.ps1",
    "open_web_ai_profile.ps1",
    "provider_registry.json",
    "browser_provider_pool.py",
    "recipes/chatgpt_web.json",
    "recipes/claude_web.json",
    "recipes/gemini_web.json",
    "recipes/perplexity_web.json",
    "recipes/grok_web.json",
    "recipes/test_harness.json",
    "recipes/test_harness_campaign.json",
    "recipes/test_harness_semantic.json",
    "browser_ai_worker.py",
    "programming_browser_loop.py",
    "simple_browser_task.py",
    "browser_task_state.py",
    "durable_browser_task.py",
    "sandbox_recovery.py",
    "build_b19_code_sandbox.py",
    "run_b09_b14_physical_gate.ps1",
    "run_b15_b18_physical_gate.ps1",
    "run_b15_b18_physical_task.py",
    "run_b20_code_gate.ps1",
    "run_b20_code_gate.py",
    "finalize_browser_field.py",
    "run_field_campaign.py",
    "run_browser_restart_gate.ps1",
    "run_w14b_real_session_gate.ps1",
    "run_b29_b30_full_field_gate.ps1",
    "real_code_candidate.py",
    "run_b38_real_ceo_candidate.py",
    "run_b38_real_ceo_candidate.ps1",
    "first_trial_safety.py",
    "first_trial_orchestrator.py",
    "run_first_trial_gate.ps1",
    "recover_first_trial.ps1",
]

ROOT_FILES={
    "EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd":"ceo-browser/EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd",
    "RECUPERAR_PRUEBA_CEO.cmd":"ceo-browser/RECUPERAR_PRUEBA_CEO.cmd",
    "EJECUTAR_B38_CANDIDATE.cmd":"ceo-browser/EJECUTAR_B38_CANDIDATE.cmd",
    "EJECUTAR_W14B_SESION_REAL.cmd":"ceo-browser/EJECUTAR_W14B_SESION_REAL.cmd",
}

README="""CEO DE IAs — PRIMERA PRUEBA BROWSER LAB

1. Este paquete es un LAB portátil. NO actualiza CEO estable.
2. El motor browser es multi-proveedor: ChatGPT, Claude, Gemini, Perplexity y Grok.
3. Esta primera validación física usa ChatGPT porque conserva la sesión que ya abriste; no es una dependencia arquitectónica.
4. La campaña funcional NO reinicia Chrome entre turnos; utiliza una única sesión para evitar aperturas/pestañas innecesarias.
5. Para certificar primero W14-B (sesión real + cierre/reapertura), doble clic en EJECUTAR_W14B_SESION_REAL.cmd.\n6. Para la campaña funcional completa, doble clic en EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd.\n6. El lanzador realiza preflight y después una única campaña B14 -> B18 -> B20 -> B29/B30.
7. Si el proveedor web requiere login, hazlo manualmente. No se automatiza CAPTCHA/2FA.
8. Cada intento usa su propio trial_id y nunca reutiliza evidencias de intentos anteriores.
9. Si termina GO, B38 NO se inicia automáticamente.
10. Solo entonces, y de forma separada, puedes lanzar EJECUTAR_B38_CANDIDATE.cmd.
11. RECUPERAR_PRUEBA_CEO.cmd cierra solo procesos Chrome/Edge que usen el perfil exclusivo del LAB.

LIMITES
- Sin OpenAI API.
- Sin compras.
- Sin commit/push/merge del candidato.
- Sin current.json.
- Sin promoción a producción.
- Evidencias: %LOCALAPPDATA%\CEO de IAs\evidence
"""

LAUNCHER_TEMPLATE=r"""@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ceo_core\browser_ai\run_first_trial_gate.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo [NO-GO] La prueba no ha sido autorizada.
  pause
  exit /b %RC%
)
echo [GO] B29-B30 superado. B38 sigue separado.
pause
"""

RECOVERY_TEMPLATE=r"""@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ceo_core\browser_ai\recover_first_trial.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
"""

B38_TEMPLATE=r"""@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0ceo_core\browser_ai\run_b38_real_ceo_candidate.ps1"
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
"""


def copy(src:Path,dst:Path)->None:
    if not src.is_file():
        raise RuntimeError(f"missing source: {src}")
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst)


def main()->None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base package: {BASE}")
    shutil.rmtree(ROOT,ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    # Browser-first runtime from the qualified branch snapshot.
    copy(CORE_SRC/"ceo_stdlib_work_mode.py",ROOT/"scripts"/"ceo_stdlib_work_mode.py")
    copy(CORE_SRC/"routing.py",ROOT/"ceo_core"/"routing.py")
    copy(CORE_SRC/"providers"/"chatgpt_web.py",ROOT/"ceo_core"/"providers"/"chatgpt_web.py")

    for rel in BROWSER_FILES:
        copy(SRC/rel,ROOT/"ceo_core"/"browser_ai"/rel)

    # Root launchers are intentionally simple and point into the embedded LAB.
    (ROOT/"EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd").write_text(LAUNCHER_TEMPLATE,encoding="utf-8",newline="\r\n")
    (ROOT/"RECUPERAR_PRUEBA_CEO.cmd").write_text(RECOVERY_TEMPLATE,encoding="utf-8",newline="\r\n")
    (ROOT/"EJECUTAR_B38_CANDIDATE.cmd").write_text(B38_TEMPLATE,encoding="utf-8",newline="\r\n")
    copy(SRC/"EJECUTAR_W14B_SESION_REAL.cmd",ROOT/"EJECUTAR_W14B_SESION_REAL.cmd")
    (ROOT/"PRIMERA_PRUEBA_README.txt").write_text(README,encoding="utf-8")

    marker={
        "schema_version":2,
        "artifact_kind":"ceo-browser-first-trial-lab",
        "build_id":BUILD_ID,
        "source_sha":SOURCE_SHA,
        "campaign_architecture":"single-session-trial-isolated-v2",
        "installable_update":False,
        "stable_channel_modified":False,
        "current_json_modified":False,
        "production_ready":False,
        "field_verified":False,
        "b38_automatic":False,
        "no_api_required":True,
        "automatic_merge":False,
        "automatic_purchase":False,
        "browser_profile":"%LOCALAPPDATA%\\CEO de IAs\\browser-profile",
    }
    (ROOT/"CEO_FIRST_TRIAL_LAB.json").write_text(json.dumps(marker,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    manifest={}
    for p in sorted(x for x in ROOT.rglob("*") if x.is_file()):
        rel=p.relative_to(ROOT).as_posix()
        manifest[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
    (ROOT/"CEO_FIRST_TRIAL_MANIFEST.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")

    OUT.unlink(missing_ok=True)
    fixed=(2026,9,21,22,0,0)
    with zipfile.ZipFile(OUT,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(x for x in ROOT.rglob("*") if x.is_file()):
            rel=p.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo(rel,date_time=fixed)
            info.create_system=0
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0
            z.writestr(info,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)

    with zipfile.ZipFile(OUT) as z:
        bad=z.testzip()
        if bad:
            raise RuntimeError(f"bad zip member: {bad}")
        names=set(z.namelist())

    required={
        "EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd",
        "RECUPERAR_PRUEBA_CEO.cmd",
        "EJECUTAR_B38_CANDIDATE.cmd",
        "EJECUTAR_W14B_SESION_REAL.cmd",
        "PRIMERA_PRUEBA_README.txt",
        "CEO_FIRST_TRIAL_LAB.json",
        "CEO_FIRST_TRIAL_MANIFEST.json",
        "ceo_core/browser_ai/first_trial_orchestrator.py",
        "ceo_core/browser_ai/run_field_campaign.py",
        "ceo_core/browser_ai/open_web_ai_profile.ps1",
        "ceo_core/browser_ai/run_b29_b30_full_field_gate.ps1",
        "ceo_core/browser_ai/run_w14b_real_session_gate.ps1",
        "ceo_core/browser_ai/run_b38_real_ceo_candidate.py",
    }
    missing=sorted(required-names)
    if missing:
        raise RuntimeError(f"missing LAB entries: {missing}")

    qualification={
        **marker,
        "artifact":OUT.name,
        "sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),
        "size_bytes":OUT.stat().st_size,
        "entry_count":len(names),
        "required_entries_verified":True,
    }
    (SRC/"CEO_FIRST_TRIAL_LAB_QUALIFICATION.json").write_text(json.dumps(qualification,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(qualification,ensure_ascii=False))


if __name__=="__main__":
    main()
