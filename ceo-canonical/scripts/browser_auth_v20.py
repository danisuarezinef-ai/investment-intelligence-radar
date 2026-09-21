from __future__ import annotations

import os
import subprocess
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
        print("[FAIL] No se encontro Chrome ni Edge.")
        return 3
    name = os.getenv("CEO_BROWSER_NAME", "chatgpt-browser-live")
    local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
    profile = local / "CEO de IAs" / "browser_profiles" / name
    profile.mkdir(parents=True, exist_ok=True)
    outdir = Path(os.environ.get("CEO_VALIDATION_OUT", str(Path.home() / "Desktop" / "CEO_VALIDATION_RESULTS")))
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "browser_path_v20.txt").write_text(str(browser), encoding="utf-8")
    (outdir / "browser_profile_v20.txt").write_text(str(profile), encoding="utf-8")
    print(f"[INFO] Navegador: {browser}")
    print(f"[INFO] Perfil COMPARTIDO con la prueba: {profile}")
    print("[INFO] Abriendo ChatGPT para comprobar autenticacion...")
    subprocess.Popen([
        str(browser), f"--user-data-dir={profile}", "--no-first-run",
        "--no-default-browser-check", "--new-window", "https://chatgpt.com/"
    ], close_fds=True)
    print("\nSi hace falta, inicia sesion. Cuando veas el cuadro normal de ChatGPT:")
    print("  1. CIERRA esa ventana de ChatGPT.")
    print("  2. Vuelve aqui y pulsa ENTER.")
    input("\nPulsa ENTER cuando la ventana este cerrada: ")
    print("[PASS] Perfil de autenticacion preparado para EL MISMO provider de v20.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
