from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import venv

REQUIRED_IMPORTS = ("fastapi", "uvicorn", "pydantic", "psutil", "playwright", "httpx", "cryptography", "ceo_app.main")


def tail(text: str, limit: int = 12000) -> str:
    return (text or "")[-limit:]


def run(cmd: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), env=env, text=True, capture_output=True, timeout=900)


def import_check(python: Path, root: Path) -> dict:
    code = (
        "import importlib,json; "
        f"mods={REQUIRED_IMPORTS!r}; "
        "[importlib.import_module(m) for m in mods]; "
        "print(json.dumps({'ok':True,'modules':mods}))"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    proc = run([str(python), "-c", code], cwd=root, env=env)
    return {
        "returncode": proc.returncode,
        "stdout_tail": tail(proc.stdout),
        "stderr_tail": tail(proc.stderr),
        "ok": proc.returncode == 0,
    }


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--status", required=True)
    ap.add_argument("--no-install", action="store_true")
    ns = ap.parse_args()

    root = Path(ns.root).resolve()
    status_path = Path(ns.status).resolve()
    status_path.parent.mkdir(parents=True, exist_ok=True)
    venv_dir = root / ".ceo-web-runtime"
    req = root / "runtime" / "web_requirements.txt"
    result: dict = {
        "status": "BLOCKED",
        "root": str(root),
        "system_python": sys.executable,
        "isolated_runtime": str(venv_dir),
        "requirements": str(req),
        "production_verified": False,
    }
    try:
        system_check = import_check(Path(sys.executable), root)
        result["system_import_check"] = system_check
        if system_check["ok"]:
            result.update(status="READY", runtime="system", python_executable=sys.executable, installed=False)
            status_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
            return 0

        if ns.no_install:
            result.update(error="system_web_stack_import_failed_and_install_disabled")
            status_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
            return 4

        py = venv_python(venv_dir)
        if not py.exists():
            venv.EnvBuilder(with_pip=True, clear=False).create(str(venv_dir))
        if not py.exists():
            raise RuntimeError(f"No se pudo crear Python aislado en {py}")

        isolated_before = import_check(py, root)
        result["isolated_import_check_before"] = isolated_before
        if not isolated_before["ok"]:
            if not req.exists():
                raise RuntimeError(f"Falta requirements web: {req}")
            install = run(
                [str(py), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "-r", str(req)],
                cwd=root,
            )
            result["pip_install"] = {
                "returncode": install.returncode,
                "stdout_tail": tail(install.stdout),
                "stderr_tail": tail(install.stderr),
            }
            if install.returncode != 0:
                raise RuntimeError("pip no pudo instalar las dependencias web en el entorno aislado")

        isolated_after = import_check(py, root)
        result["isolated_import_check_after"] = isolated_after
        if not isolated_after["ok"]:
            raise RuntimeError("El stack web sigue sin poder importarse tras reparar el entorno aislado")

        result.update(status="READY", runtime="isolated", python_executable=str(py), installed=True)
        status_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 0
    except Exception as exc:
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        status_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
        return 6


if __name__ == "__main__":
    raise SystemExit(main())
