from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.desktop_integration import ApplicationRegistry, DesktopBrowserIntegrationCore, WindowsDesktopBackend
from ceo_core.models import ProjectState


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--physical-smoke",action="store_true",help="Allow one visible Chrome launch after discovery")
    args=ap.parse_args()
    state=ProjectState(id="windows-desktop-validation",goal="validate desktop/browser 1-10")
    core=DesktopBrowserIntegrationCore(ApplicationRegistry())
    core.registry.initialize(state)
    apps=core.registry.discover(state)
    out={
        "platform":os.name,
        "windows":os.name=="nt",
        "applications":[{"app_id":a.app_id,"discovered":a.discovered,"executable":a.executable} for a in apps],
        "local_preflight":core.local_preflight(state),
        "physical_smoke_requested":args.physical_smoke,
        "physical_smoke_executed":False,
    }
    if os.name!="nt":
        out["status"]="NOT_RUN_NOT_WINDOWS"
        print(json.dumps(out,indent=2)); return 2
    try:
        backend=WindowsDesktopBackend()
        out["desktop_backend_capabilities"]=sorted(backend.capabilities())
        out["windows_visible_count"]=len(backend.list_windows()) if "list_windows" in backend.capabilities() else None
        chrome=core.registry.get(state,"chrome")
        if args.physical_smoke and chrome and chrome.discovered and chrome.executable:
            result=backend.launch(chrome.executable,["--new-window","about:blank"])
            out["physical_smoke_executed"]=True; out["chrome_launch"]=result
        out["status"]="PREFLIGHT_PASS" if out["local_preflight"]["pass"] else "PREFLIGHT_FAIL"
    except Exception as exc:
        out["status"]="FAIL"; out["error"]=f"{type(exc).__name__}: {exc}"
    print(json.dumps(out,indent=2)); return 0 if out["status"] in {"PREFLIGHT_PASS"} else 1

if __name__=="__main__": raise SystemExit(main())
