from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

VERSION = "1.5.79-rc1-productive-resume-gate"
RELEASE_SEQUENCE = 303
RELEASE_ID = "dev303-1.5.79-rc1-productive-resume-gate"
MANIFEST_URL = "https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/DEV303_MANIFEST_UNSIGNED.json"
ACTIVE_MANIFEST_URL = "https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-update-channel/ceo-updates/manifest.json"
EXPECTED_ACTIVE = "1.5.78-rc1-reliable-update-handoff"


def fetch_json(url: str, timeout: int = 30) -> dict:
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(
        url + sep + f"ceo_transition={int(time.time())}",
        headers={"Cache-Control":"no-cache, no-store","Pragma":"no-cache","User-Agent":"CEO-de-IAs-DEV303-transition"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def data_root() -> Path:
    return Path(os.getenv("LOCALAPPDATA") or (Path.home()/"AppData"/"Local"))/"CEO de IAs"


def current_pointer() -> dict:
    p=data_root()/"updates"/"current.json"
    if not p.is_file():
        raise RuntimeError("CURRENT_POINTER_MISSING")
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"ok":False,"status":"WINDOWS_REQUIRED"}))
        return 6

    pointer=current_pointer()
    current=str(pointer.get("version") or "")
    root=Path(str(pointer.get("root") or "")).resolve()
    if current == VERSION:
        print(json.dumps({"ok":True,"status":"ALREADY_INSTALLED","version":VERSION},indent=2))
        return 0
    if current != EXPECTED_ACTIVE:
        print(json.dumps({"ok":False,"status":"UNEXPECTED_ACTIVE_VERSION","current":current,"expected":EXPECTED_ACTIVE},indent=2))
        return 7
    if not (root/"ceo_core"/"prepared_release_bridge.py").is_file():
        print(json.dumps({"ok":False,"status":"ACTIVE_RUNTIME_NOT_FOUND","root":str(root)},indent=2))
        return 8

    # If an earlier invocation already published DEV303, do not attempt to replay it.
    try:
        remote=fetch_json(ACTIVE_MANIFEST_URL,20)
        if int(remote.get("release_sequence") or 0) == RELEASE_SEQUENCE and str(remote.get("release_id") or "") == RELEASE_ID:
            print(json.dumps({"ok":True,"status":"ALREADY_PUBLISHED","version":VERSION,"release_sequence":RELEASE_SEQUENCE},indent=2))
            return 0
    except Exception:
        pass

    sys.path.insert(0,str(root))
    from ceo_core.prepared_release_bridge import PreparedReleaseBridge

    original_allowed=PreparedReleaseBridge._allowed

    def corrected_allowed(self, url: str) -> bool:
        p=urlparse(str(url or ""))
        repo=str(self.channel.intended_repository or "").strip()
        branch=str(self.publisher.policy.branch or "").strip()
        path_prefix=str(self.publisher.policy.path_prefix or "ceo-updates/").lstrip("/")
        prefix=f"/{repo}/{branch}/{path_prefix}"
        return bool(repo and branch and p.scheme=="https" and p.netloc=="raw.githubusercontent.com" and p.path.startswith(prefix))

    PreparedReleaseBridge._allowed=corrected_allowed
    try:
        bridge=PreparedReleaseBridge()
        result=bridge.activate(MANIFEST_URL)
    finally:
        PreparedReleaseBridge._allowed=original_allowed

    print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
    if bool(result.get("ok")) and str(result.get("status") or "") == "PUBLISHED":
        return 0
    if str(result.get("status") or "") == "ANTI_REPLAY_BLOCKED":
        try:
            remote=fetch_json(ACTIVE_MANIFEST_URL,20)
            if int(remote.get("release_sequence") or 0) == RELEASE_SEQUENCE and str(remote.get("release_id") or "") == RELEASE_ID:
                return 0
        except Exception:
            pass
    return 10


if __name__=="__main__":
    raise SystemExit(main())
