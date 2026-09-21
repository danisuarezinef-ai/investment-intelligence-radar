from __future__ import annotations

import hashlib
import json
import os
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.89-rc1-native-transport-integrity.zip"
SRC = REPO / "ceo-updates" / "dev313-inspect-routing"
LAB = REPO / "ceo-browser"
ROOT = pathlib.Path(os.environ.get("CEO_BROWSER_LAB_BUILD_ROOT", "/tmp/ceo-browser-first-lab"))
OUT = LAB / "CEO_BROWSER_FIRST_LAB.zip"

CMD = r"""@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "CEO_ALLOW_OPTIONAL_API=0"
set "GEMINI_API_KEY="
set "CEO_KEY_IN_BROWSER=0"

set "PY="
for %%P in (pythonw.exe python.exe pyw.exe py.exe) do (
  if not defined PY (
    where %%P >nul 2>nul
    if not errorlevel 1 set "PY=%%P"
  )
)
if not defined PY exit /b 7

if /I "%PY%"=="py.exe" (
  start "" /b py.exe -3 scripts\ceo_stdlib_work_mode.py
) else if /I "%PY%"=="pyw.exe" (
  start "" /b pyw.exe -3 scripts\ceo_stdlib_work_mode.py
) else (
  start "" /b "%PY%" scripts\ceo_stdlib_work_mode.py
)
exit /b 0
"""

VBS = r"""Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = Chr(34) & base & "\ABRIR_CEO_BROWSER_LAB.cmd" & Chr(34)
sh.Run "cmd.exe /c " & cmd, 0, False
"""

LOGIN_VBS = r"""Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
ps = Chr(34) & base & "\ceo_core\browser_ai\open_chatgpt_profile.ps1" & Chr(34)
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & ps, 0, False
"""

README = """CEO DE IAs — BROWSER FIRST LAB

OBJETIVO
-------
Validar que CEO puede usar una IA web mediante Chrome sin depender de ninguna API.

ESTE PAQUETE:
- NO es una actualización.
- NO cambia la versión instalada.
- NO modifica current.json.
- NO publica nada en el canal estable.
- NO necesita OpenAI API.
- NO necesita Gemini API.
- Fuerza CEO_ALLOW_OPTIONAL_API=0.

PRIMER USO
----------
1. Doble clic en PREPARAR_SESION_CHATGPT_CEO.vbs
2. Si ChatGPT lo pide, inicia sesión manualmente una sola vez.
3. Cierra esa ventana cuando hayas terminado el login.
4. Doble clic en ABRIR_CEO_BROWSER_LAB.vbs

CEO reutilizará el perfil persistente:
%LOCALAPPDATA%\CEO de IAs\browser-profile

ESTADO
------
Este LAB es pre-campo. No se considera funcional hasta que ChatGPT web real
complete dos turnos y, después, un objetivo pequeño produzca un entregable verificado.
"""


def copy_file(src: pathlib.Path, dst: pathlib.Path) -> None:
    if not src.is_file():
        raise RuntimeError(f"missing source: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    if not BASE.is_file():
        raise RuntimeError(f"missing base package: {BASE}")

    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    # Browser-first CEO source. This is a lab-only replacement, not a release.
    copy_file(SRC / "ceo_stdlib_work_mode.py", ROOT / "scripts" / "ceo_stdlib_work_mode.py")
    copy_file(SRC / "routing.py", ROOT / "ceo_core" / "routing.py")
    copy_file(SRC / "providers" / "chatgpt_web.py", ROOT / "ceo_core" / "providers" / "chatgpt_web.py")
    copy_file(SRC / "browser_ai" / "windows_chatgpt_cdp_driver.ps1", ROOT / "ceo_core" / "browser_ai" / "windows_chatgpt_cdp_driver.ps1")
    copy_file(SRC / "browser_ai" / "open_chatgpt_profile.ps1", ROOT / "ceo_core" / "browser_ai" / "open_chatgpt_profile.ps1")
    copy_file(SRC / "browser_ai" / "recipes" / "chatgpt_web.json", ROOT / "ceo_core" / "browser_ai" / "recipes" / "chatgpt_web.json")

    (ROOT / "ABRIR_CEO_BROWSER_LAB.cmd").write_text(CMD, encoding="utf-8", newline="\r\n")
    (ROOT / "ABRIR_CEO_BROWSER_LAB.vbs").write_text(VBS, encoding="utf-8", newline="\r\n")
    (ROOT / "PREPARAR_SESION_CHATGPT_CEO.vbs").write_text(LOGIN_VBS, encoding="utf-8", newline="\r\n")
    (ROOT / "CEO_BROWSER_FIRST_LAB_README.txt").write_text(README, encoding="utf-8")

    # Marker prevents this portable artifact from being confused with an updater release.
    marker = {
        "artifact_kind": "browser-first-field-lab",
        "installable_update": False,
        "stable_channel_modified": False,
        "base_package": BASE.name,
        "no_api_required": True,
        "optional_api_enabled_by_default": False,
        "primary_ai_surface": "chatgpt-web",
        "browser_profile": "%LOCALAPPDATA%\\CEO de IAs\\browser-profile",
        "field_verified": False,
        "production_ready": False,
    }
    (ROOT / "CEO_BROWSER_FIRST_LAB.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    OUT.unlink(missing_ok=True)
    fixed = (2026, 9, 21, 21, 30, 0)
    files = sorted(p for p in ROOT.rglob("*") if p.is_file())
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in files:
            rel = p.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(rel, date_time=fixed)
            info.create_system = 0
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0
            z.writestr(info, p.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    with zipfile.ZipFile(OUT) as z:
        bad = z.testzip()
        if bad:
            raise RuntimeError(f"bad zip member: {bad}")
        names = set(z.namelist())

    required = {
        "scripts/ceo_stdlib_work_mode.py",
        "ceo_core/providers/chatgpt_web.py",
        "ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1",
        "ceo_core/browser_ai/open_chatgpt_profile.ps1",
        "ceo_core/browser_ai/recipes/chatgpt_web.json",
        "ABRIR_CEO_BROWSER_LAB.vbs",
        "PREPARAR_SESION_CHATGPT_CEO.vbs",
        "CEO_BROWSER_FIRST_LAB.json",
    }
    missing = sorted(required - names)
    if missing:
        raise RuntimeError(f"missing lab files: {missing}")

    data = OUT.read_bytes()
    qualification = {
        **marker,
        "artifact": OUT.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "entry_count": len(names),
    }
    (LAB / "CEO_BROWSER_FIRST_LAB_QUALIFICATION.json").write_text(
        json.dumps(qualification, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(qualification, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
