from __future__ import annotations

import argparse
import compileall
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.mobile_dev_queue import MobileDevelopmentQueue
from ceo_core.release_readiness_v5 import qualify_release_v5
from ceo_core.self_dev_handoff import validate_self_development_receipt
from ceo_core.update_diagnostics import UpdateDiagnostics
from ceo_core.update_failure_lab import UpdateFailureLab
from ceo_core.update_state_machine import UpdateStateMachine
from ceo_core.update_transaction import UpdateTransactionJournal


def _verify_package_contract() -> bool:
    try:
        row = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
        for rel in row.get("required_paths") or []:
            if not (ROOT / str(rel)).is_file():
                return False
        for rel, expected in (row.get("file_hashes") or {}).items():
            path = ROOT / str(rel)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != str(expected):
                return False
        return True
    except Exception:
        return False


def _security_audit() -> bool:
    try:
        cp = subprocess.run([sys.executable, str(ROOT / "scripts" / "security_audit.py")], cwd=str(ROOT), capture_output=True, text=True, timeout=60)
        return cp.returncode == 0 and "'findings': []" in cp.stdout
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default="")
    ns = ap.parse_args()
    results = {}
    results["fault_lab"] = UpdateFailureLab.run_matrix(repetitions=250)
    with tempfile.TemporaryDirectory(prefix="ceo-dev85-") as td:
        base = Path(td)
        updates = base / "updates"; updates.mkdir()
        (updates / "progress.json").write_text(json.dumps({"phase":"preflight_failed","reason":"synthetic","updated_at_epoch":1}), encoding="utf-8")
        diag = UpdateDiagnostics(updates).bundle(); results["diagnostics"] = diag
        view = UpdateStateMachine.view(status={"current_version":"x","staged":[]}, progress={"phase":"preflight_failed","percent":100})
        results["state_machine"] = view
        journal = UpdateTransactionJournal(updates)
        journal.append("download", version="x"); journal.append("preflight_ok", version="x"); journal.append("healthy", version="x")
        results["transaction"] = journal.verify()
        queue = MobileDevelopmentQueue(base)
        queue.enqueue(kind="simulate", title="safe")
        rejected = False
        try:
            queue.enqueue(kind="simulate", title="unsafe", capabilities=["publish"])
        except PermissionError:
            rejected = True
        results["mobile_queue"] = {"safe": queue.snapshot(), "unsafe_rejected": rejected}
        receipt = {
            "candidate_id":"synthetic", "base_version":"x", "candidate_version":"y", "changed_files":["a.py"],
            "tests":{"passed":1,"failed":0}, "published":False, "installed":False, "auto_promoted":False,
            "safety":{"stable_unchanged":True,"automatic_spending_false":True,"automatic_publication_false":True,"automatic_installation_false":True},
        }
        results["self_dev_handoff"] = validate_self_development_receipt(receipt)
    gates = {
        "compileall": bool(compileall.compile_dir(str(ROOT / "ceo_core"), quiet=1) and compileall.compile_dir(str(ROOT / "scripts"), quiet=1)),
        "package_contract": _verify_package_contract(),
        "security_audit": _security_audit(),
        "fault_lab": results["fault_lab"]["ok"],
        "diagnostics": results["diagnostics"]["diagnosis"]["code"] == "preflight_failed",
        "update_state_machine": results["state_machine"]["state"] == "blocked",
        "transaction_journal": results["transaction"]["ok"],
        "mobile_dev_queue": results["mobile_queue"]["unsafe_rejected"],
        "self_dev_handoff": results["self_dev_handoff"]["ok"],
    }
    results["readiness"] = qualify_release_v5(gates, windows_physical_verified=False)
    results["ok"] = bool(results["readiness"]["local_candidate_ready"] and not results["readiness"]["production_ready"])
    text = json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        Path(ns.json).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if results["ok"] else 7

if __name__ == "__main__":
    raise SystemExit(main())
