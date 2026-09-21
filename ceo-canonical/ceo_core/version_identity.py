from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "CEO_UPDATE_PACKAGE.json"
def current_version() -> str:
    try:
        data = json.loads(CONTRACT.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"VERSION_CONTRACT_UNREADABLE:{type(exc).__name__}") from exc
    version = str(data.get("app_version") or "").strip()
    if not version:
        raise RuntimeError("VERSION_CONTRACT_EMPTY")
    return version
def assert_runtime_version(value: str) -> str:
    expected = current_version()
    actual = str(value or "").strip()
    if actual != expected:
        raise RuntimeError(f"VERSION_IDENTITY_MISMATCH:{actual}!={expected}")
    return actual
