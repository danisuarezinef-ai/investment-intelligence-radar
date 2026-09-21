from __future__ import annotations

"""Isolated startup preflight for a staged CEO update.

Runs the candidate's real CEOEngine and HTTP health endpoint against a disposable
CEO_DATA_DIR.  It never activates the candidate and never opens a browser.  A
failed preflight leaves the currently running CEO untouched.
"""

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path


def _load_work_mode(root: Path):
    script = root / "scripts" / "ceo_stdlib_work_mode.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    spec = importlib.util.spec_from_file_location("ceo_candidate_work_mode", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load candidate work-mode module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--expected-version", required=True)
    ap.add_argument("--sandbox-parent", required=True)
    ap.add_argument("--timeout", type=float, default=35.0)
    ns = ap.parse_args()

    root = Path(ns.root).resolve()
    sandbox_parent = Path(ns.sandbox_parent).resolve()
    sandbox_parent.mkdir(parents=True, exist_ok=True)
    sandbox = Path(tempfile.mkdtemp(prefix="candidate-", dir=str(sandbox_parent)))
    old_data = os.environ.get("CEO_DATA_DIR")
    old_path = list(sys.path)
    server = None
    thread = None
    engine = None
    try:
        os.environ["CEO_DATA_DIR"] = str(sandbox)
        sys.path.insert(0, str(root))
        mod = _load_work_mode(root)
        if str(getattr(mod, "APP_VERSION", "")) != str(ns.expected_version):
            raise RuntimeError(f"candidate version mismatch: {getattr(mod, 'APP_VERSION', None)!r}")
        engine = mod.CEOEngine(None)
        mod.Handler.engine = engine
        server = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
        port = int(server.server_address[1])
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        deadline = time.time() + max(5.0, ns.timeout)
        last_error = "health unavailable"
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.0) as resp:
                    payload = json.loads(resp.read(1024 * 1024).decode("utf-8"))
                if payload.get("ok") is True and str(payload.get("version") or "") == str(ns.expected_version):
                    print(json.dumps({"ok": True, "version": ns.expected_version, "port": port, "sandbox": str(sandbox)}, ensure_ascii=False))
                    return 0
                last_error = f"health payload not ready: {payload}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(0.15)
        raise RuntimeError(last_error)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 7
    finally:
        if server is not None:
            try: server.shutdown()
            except Exception: pass
            try: server.server_close()
            except Exception: pass
        if thread is not None:
            try: thread.join(timeout=2)
            except Exception: pass
        if engine is not None:
            try: engine.call(engine.shutdown(), timeout=15)
            except Exception: pass
        sys.path[:] = old_path
        if old_data is None:
            os.environ.pop("CEO_DATA_DIR", None)
        else:
            os.environ["CEO_DATA_DIR"] = old_data
        shutil.rmtree(sandbox, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
