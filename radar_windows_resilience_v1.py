"""Windows observer resilience contract for Radar PAPER.
Local desktop state is presentation-only; authoritative PAPER state stays cloud/durable.
"""
from __future__ import annotations
import json, os, tempfile
from pathlib import Path
REAL_TRADING=False
SAFE_KEYS=("window","metric","selected_tab","expanded_panels")
def sanitize_ui_state(data):
    data=data if isinstance(data,dict) else {}
    return {k:data[k] for k in SAFE_KEYS if k in data}
def atomic_save_ui_state(path,data):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    payload={"schema":1,"real_trading":False,"ui":sanitize_ui_state(data)}
    fd,tmp=tempfile.mkstemp(prefix=path.name+".",dir=str(path.parent))
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(payload,f,sort_keys=True); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return payload
def load_ui_state(path):
    try:
        raw=json.loads(Path(path).read_text(encoding="utf-8"))
        if raw.get("schema")!=1 or raw.get("real_trading") is not False:return {}
        return sanitize_ui_state(raw.get("ui"))
    except (OSError,ValueError,TypeError):return {}
def recovery_plan(cloud_available,exact_restore,reconciled,lease_ok):
    if not cloud_available:return {"mode":"OFFLINE_READ_ONLY","engine_start":False,"paper_mutation":False}
    if not (exact_restore and reconciled and lease_ok):return {"mode":"RECOVERY_BLOCKED","engine_start":False,"paper_mutation":False}
    return {"mode":"CLOUD_OBSERVER","engine_start":False,"paper_mutation":False}
