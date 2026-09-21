from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

SECRET_KEYS=("api_key","token","secret","password","authorization","credential")


def _redact(value: Any, key: str = "") -> Any:
    if any(k in key.lower() for k in SECRET_KEYS): return "[REDACTED]"
    if isinstance(value,dict): return {str(k):_redact(v,str(k)) for k,v in value.items()}
    if isinstance(value,list): return [_redact(v,key) for v in value]
    if isinstance(value,str):
        v=re.sub(r"AIza[0-9A-Za-z_-]{20,}","[REDACTED_GOOGLE_KEY]",value)
        v=re.sub(r"sk-[0-9A-Za-z_-]{20,}","[REDACTED_API_KEY]",v)
        return v
    return value


def build_diagnostic_support_bundle_v1(output_zip: str | Path, *, evidence: dict[str, Any]) -> dict[str, Any]:
    out=Path(output_zip);out.parent.mkdir(parents=True,exist_ok=True)
    clean=_redact(evidence)
    payload=json.dumps(clean,ensure_ascii=False,indent=2,sort_keys=True).encode("utf-8")
    with zipfile.ZipFile(out,"w",compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("diagnostic.json",payload)
        zf.writestr("README.txt","CEO de IAs diagnostic bundle. Secrets are redacted. No user project contents are included.\n")
    blob=out.read_bytes()
    text=payload.decode("utf-8",errors="ignore")
    leaked=bool(re.search(r"AIza[0-9A-Za-z_-]{20,}|sk-[0-9A-Za-z_-]{20,}",text))
    return {"ok":not leaked,"path":str(out),"sha256":hashlib.sha256(blob).hexdigest(),"size_bytes":len(blob),"secret_leak_detected":leaked,"user_project_contents_included":False,"entries":2}
