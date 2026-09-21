from __future__ import annotations

"""Build the one-time Windows updater bootstrap bundle.

This is intentionally *not* the normal update artifact. Its only job is to install
CEO once under LocalAppData with a private runtime and a built-in signed update
channel. After this bootstrap, future releases should arrive through the in-app
updater and this bundle should no longer be needed.
"""

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXACT_ROOT = {
    "ABRIR_CEO.cmd",
    "INSTALAR_CEO_ACTUALIZADOR.cmd",
    "pyproject.toml",
    "CEO_UPDATE_PACKAGE.json",
    "RC1_FREEZE_POLICY.json",
    "LEEME_INSTALACION_UPDATER.txt",
}
DIRS = {"ceo_core", "scripts", "schemas", "ceo_app", "assets"}
EXCLUDED_PARTS = {"__pycache__", ".pytest_cache", ".git"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def members(source: Path) -> list[Path]:
    out: list[Path] = []
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(source)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        low = rel.as_posix().lower()
        if low.endswith((".pyc", ".pyo", ".part")):
            continue
        if "private.key" in low or "release_secrets" in low:
            continue
        if path.name.upper().startswith(("ABRIR_CEO_", "VALIDAR_", "REANUDAR_")):
            continue
        if rel.as_posix() in EXACT_ROOT or (rel.parts and rel.parts[0] in DIRS):
            out.append(path)
    return sorted(set(out))


def build(source: Path, output: Path) -> dict:
    required = [
        source / "INSTALAR_CEO_ACTUALIZADOR.cmd",
        source / "scripts" / "install_windows_bootstrap.py",
        source / "ceo_core" / "update_trust.json",
        source / "ceo_core" / "in_app_updater.py",
        source / "scripts" / "launch_current.py",
        source / "scripts" / "ceo_stdlib_work_mode.py",
    ]
    missing = [str(p.relative_to(source)) for p in required if not p.is_file()]
    if missing:
        raise RuntimeError("Bootstrap incompleto: " + ", ".join(missing))

    selected = members(source)
    if len(selected) < 25:
        raise RuntimeError(f"Bootstrap sospechosamente pequeño: {len(selected)} archivos")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in selected:
            rel = path.relative_to(source).as_posix()
            zf.write(path, rel)

    result = {
        "artifact": str(output),
        "sha256": sha256(output),
        "size_bytes": output.stat().st_size,
        "files": len(selected),
        "entrypoint": "INSTALAR_CEO_ACTUALIZADOR.cmd",
        "purpose": "one-time updater bootstrap; future releases in-app",
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT))
    ap.add_argument("--output", required=True)
    ns = ap.parse_args()
    result = build(Path(ns.source).resolve(), Path(ns.output).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
