from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "1.4.88-rc1-autonomous-productive-execution"


def package_contract() -> dict:
    row = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    bad: list[str] = []
    if row.get("app_version") != CANDIDATE:
        bad.append("version")
    for rel in row.get("required_paths", []):
        p = ROOT / rel
        if not p.is_file():
            bad.append(f"missing:{rel}")
            continue
        if rel == "CEO_UPDATE_PACKAGE.json":
            continue
        got = hashlib.sha256(p.read_bytes()).hexdigest()
        if got != str((row.get("file_hashes") or {}).get(rel) or ""):
            bad.append(f"hash:{rel}")
    return {"ok": not bad, "bad": bad[:30], "required": len(row.get("required_paths", [])), "hashes": len(row.get("file_hashes", {}))}


def startup_preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix="dev211-win-preflight-") as td:
        cp = subprocess.run(
            [sys.executable, "-u", str(ROOT / "scripts" / "update_candidate_preflight.py"), "--root", str(ROOT), "--expected-version", CANDIDATE, "--sandbox-parent", td, "--timeout", "25"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=45,
        )
        text = ((cp.stdout or "") + ("\n" + cp.stderr if cp.stderr else "")).strip()
        payload = {}
        for line in reversed(text.splitlines()):
            try:
                candidate = json.loads(line)
                if isinstance(candidate, dict):
                    payload = candidate
                    break
            except Exception:
                pass
        return {"ok": cp.returncode == 0 and payload.get("ok") is True and payload.get("version") == CANDIDATE, "returncode": cp.returncode, "payload": payload, "detail_tail": text[-3000:]}


def dev211_qualification() -> dict:
    cp = subprocess.run([sys.executable, str(ROOT / "scripts" / "dev211_local_qualification.py")], cwd=ROOT, env={**__import__("os").environ, "PYTHONPATH": str(ROOT)}, capture_output=True, text=True, timeout=90)
    try:
        payload = json.loads(cp.stdout)
    except Exception:
        payload = {"ok": False, "raw": (cp.stdout + cp.stderr)[-5000:]}
    return {"ok": cp.returncode == 0 and payload.get("ok") is True, "returncode": cp.returncode, "payload": payload}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--json", default="")
    ns = ap.parse_args()
    out = {
        "candidate": CANDIDATE,
        "package_contract": package_contract(),
        "startup_preflight": startup_preflight(),
        "dev211_qualification": dev211_qualification(),
        "physical_installation_executed": False,
        "production_verified": False,
        "automatic_installation": False,
    }
    out["ok"] = all(out[k]["ok"] for k in ("package_contract", "startup_preflight", "dev211_qualification"))
    text = json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if out["ok"] else 7


if __name__ == "__main__":
    raise SystemExit(main())
