from __future__ import annotations

from pathlib import Path
from typing import Any


def verify_rollback_result_v2(result: dict[str, Any], *, fallback_launcher: str | Path | None = None) -> dict[str, Any]:
    pointer = result.get("pointer") if isinstance(result, dict) else None
    launcher = result.get("launcher_path") if isinstance(result, dict) else None
    restored_pointer_ok = bool(pointer and Path(str(pointer.get("root") or "")).is_dir())
    launcher_ok = bool(launcher and Path(str(launcher)).is_file())
    fallback_ok = bool(fallback_launcher and Path(fallback_launcher).is_file())
    bundled = bool(result.get("to_bundled_fallback")) if isinstance(result, dict) else False
    usable = bool((restored_pointer_ok and launcher_ok) or (bundled and fallback_ok))
    return {
        "rollback_recorded": bool(result.get("rolled_back")) if isinstance(result, dict) else False,
        "restored_pointer_ok": restored_pointer_ok,
        "restored_launcher_ok": launcher_ok,
        "bundled_fallback": bundled,
        "bundled_fallback_launcher_ok": fallback_ok,
        "usable_recovery_path": usable,
    }
