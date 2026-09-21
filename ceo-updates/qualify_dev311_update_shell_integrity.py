from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

ROOT = pathlib.Path(os.environ["CEO_DEV311_BUILD_ROOT"]).resolve()
sys.path.insert(0, str(ROOT))


def load_launcher():
    spec = importlib.util.spec_from_file_location("dev311_launch_current", ROOT / "scripts" / "launch_current.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ui_stage_transition() -> dict:
    text = (ROOT / "scripts" / "ceo_stdlib_work_mode.py").read_text(encoding="utf-8")
    assert "let updateState=null;let updateActionBusy=false;" in text
    assert "installable=(r&&r.receipt" in text
    assert "updateState.staged=[installable" in text
    assert "setUpdateButton('Instalar y reiniciar',true,installable.version)" in text
    assert "if(phase==='ready_to_install'&&!updateActionBusy)" in text
    assert "finally{updateActionBusy=false}" in text
    assert "confirm('CEO '+version+' está verificado y listo." in text
    assert "body:JSON.stringify({version,confirm:true})" in text

    stage_slice = text[text.index("const r=await j('/api/update/stage'"):text.index("if(!installable)throw new Error", text.index("const r=await j('/api/update/stage'"))]
    assert "r.receipt" in stage_slice
    # The normal successful path must not depend on a second status call.
    before_fallback = stage_slice.split("else{const refreshed=await updateStatus(false)")[0]
    assert "await updateStatus(false)" not in before_fallback
    return {
        "receipt_authoritative": True,
        "telemetry_self_heal": True,
        "single_flight": True,
        "human_confirmation_preserved": True,
    }


def test_existing_instance_probe() -> dict:
    launcher = load_launcher()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            if self.path == "/api/health":
                body = json.dumps({"ok": True, "version": "1.5.86-test"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404); self.end_headers()

    server = None
    chosen = None
    for port in range(8765, 8781):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), H)
            chosen = port
            break
        except OSError:
            continue
    assert server is not None and chosen is not None
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        found = launcher._probe_existing_ceo()
        assert found == f"http://127.0.0.1:{chosen}", found
    finally:
        server.shutdown(); server.server_close(); t.join(timeout=2)
    return {"found": found, "port": chosen}


def test_main_reuses_existing_without_updater() -> dict:
    launcher = load_launcher()
    called = {"opened": 0, "updater": 0}

    launcher._probe_existing_ceo = lambda: "http://127.0.0.1:8777"
    launcher._open_existing_as_app = lambda url: called.__setitem__("opened", called["opened"] + 1) or "mock-browser"

    class ExplodingUpdater:
        def __init__(self, *a, **k):
            called["updater"] += 1
            raise AssertionError("updater must not initialize when an existing healthy instance is reused")

    launcher.InAppUpdater = ExplodingUpdater
    launcher._write_status = lambda payload: None

    rc = launcher.main()
    assert rc == 0
    assert called["opened"] == 1
    assert called["updater"] == 0
    return {"returncode": rc, "opened_existing": called["opened"], "updater_initialized": called["updater"]}


def test_launcher_semantics() -> dict:
    text = (ROOT / "scripts" / "launch_current.py").read_text(encoding="utf-8")
    assert "EXISTING_INSTANCE_OPENED" in text
    assert "--app={url}" in text
    assert "single_instance" in text
    assert "_probe_existing_ceo()" in text
    return {"app_mode": True, "single_instance": True}


def main():
    rows = {
        "ui": test_ui_stage_transition(),
        "probe": test_existing_instance_probe(),
        "reuse": test_main_reuses_existing_without_updater(),
        "launcher": test_launcher_semantics(),
    }
    print("DEV311_UPDATE_SHELL_INTEGRITY_PASS")
    print(rows)


if __name__ == "__main__":
    main()
