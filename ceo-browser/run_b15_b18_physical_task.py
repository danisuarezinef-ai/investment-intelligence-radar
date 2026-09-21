from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from programming_browser_loop import PowerShellChatGPTWebTransport
from simple_browser_task import BrowserArtifactTaskRunner, SafeArtifactStore


EXPECTED = "CEO_BROWSER_ARTIFACT_OK\nCANAL=CHATGPT_WEB\nAPIS=0"


def default_local() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-dir", default=str(default_local() / "CEO de IAs" / "browser-profile"))
    parser.add_argument("--output-dir", default=str(default_local() / "CEO de IAs" / "evidence"))
    parser.add_argument("--port", type=int, default=9227)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    base = Path(__file__).resolve().parent
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    transport = PowerShellChatGPTWebTransport(
        driver_path=base / "windows_chatgpt_cdp_driver.ps1",
        recipe_path=base / "recipes" / "chatgpt_web.json",
        profile_dir=args.profile_dir,
        port=args.port,
        timeout_seconds=args.timeout,
    )
    runner = BrowserArtifactTaskRunner(
        transport=transport,
        artifact_store=SafeArtifactStore(output_dir),
    )

    result = runner.run(
        objective=(
            "Crea un artefacto de validación de exactamente tres líneas. "
            "La primera línea debe ser CEO_BROWSER_ARTIFACT_OK, la segunda "
            "CANAL=CHATGPT_WEB y la tercera APIS=0. No añadas ninguna otra línea "
            "dentro del artefacto."
        ),
        acceptance=[
            "Exactly three lines inside CEO_ARTIFACT.",
            "Line 1 is CEO_BROWSER_ARTIFACT_OK.",
            "Line 2 is CANAL=CHATGPT_WEB.",
            "Line 3 is APIS=0.",
            "Finish with <CEO_DONE>true</CEO_DONE>.",
        ],
        artifact_name="B18_PRIMER_ARTEFACTO.txt",
    )

    evidence = {
        "schema_version": 1,
        "phase": "B15-B18",
        "ok": bool(result.success),
        "status": result.status,
        "api_calls": 0,
        "paid_api_calls": 0,
        "artifact_path": result.artifact_path,
        "artifact_sha256": result.artifact_sha256,
        "artifact_chars": result.artifact_chars,
        "conversation_url": result.conversation_url,
        "metadata": result.metadata,
        "failure_reason": result.failure_reason,
        "content_verified": False,
    }

    if result.success:
        actual = Path(result.artifact_path).read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        if actual != EXPECTED:
            evidence["ok"] = False
            evidence["status"] = "ARTIFACT_CONTENT_MISMATCH"
            evidence["failure_reason"] = f"unexpected artifact content: {actual!r}"
            Path(result.artifact_path).unlink(missing_ok=True)
        else:
            evidence["content_verified"] = True
            evidence["status"] = "B18_REAL_BROWSER_ARTIFACT_PASS"

    evidence_path = output_dir / "B15_B18_PHYSICAL_GATE.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
