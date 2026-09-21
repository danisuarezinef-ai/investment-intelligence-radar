from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def candidate_browsers() -> list[Path]:
    pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    pfx86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    return [
        pf / "Google" / "Chrome" / "Application" / "chrome.exe",
        pfx86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local / "Google" / "Chrome" / "Application" / "chrome.exe",
        pf / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        pfx86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        local / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]


def find_browser() -> Path | None:
    override = os.environ.get("CEO_CHROMIUM_EXECUTABLE")
    if override and Path(override).is_file():
        return Path(override)
    return next((p for p in candidate_browsers() if p.is_file()), None)


def main() -> int:
    if os.name != "nt":
        print("[FAIL] Este paso debe ejecutarse en Windows.")
        return 2

    browser = find_browser()
    if browser is None:
        print("[FAIL] No se encontro Chrome ni Edge en las rutas habituales.")
        return 3

    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    profile = local / "CEO de IAs" / "browser_profiles" / "chatgpt-browser-v14"
    profile.mkdir(parents=True, exist_ok=True)

    outdir = Path(os.environ.get("CEO_VALIDATION_OUT", str(Path.home() / "Desktop" / "CEO_VALIDATION_RESULTS")))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "browser_path_v14.txt").write_text(str(browser), encoding="utf-8")

    print(f"[INFO] Navegador detectado: {browser}")
    print(f"[INFO] Perfil CEO: {profile}")
    print("[INFO] Abriendo ChatGPT para el unico paso de autenticacion...")
    try:
        subprocess.Popen(
            [
                str(browser),
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--new-window",
                "https://chatgpt.com/",
            ],
            close_fds=True,
        )
    except Exception as exc:
        print(f"[FAIL] No se pudo abrir el navegador: {type(exc).__name__}: {exc}")
        return 4

    print()
    print("Inicia sesion si es necesario.")
    print("Cuando veas el cuadro normal para escribir a ChatGPT:")
    print("  1. CIERRA la ventana de ChatGPT que acabamos de abrir.")
    print("  2. Vuelve aqui y pulsa ENTER.")
    print("Este paso de autenticacion NO cuenta como una peticion humana de 'continua'.")
    input("\nPulsa ENTER cuando hayas cerrado esa ventana: ")
    print("[PASS] Perfil de autenticacion preparado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
