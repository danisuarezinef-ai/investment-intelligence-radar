"""Fail-closed internal update contracts. No installer execution is performed here."""
from __future__ import annotations
import hashlib
CHANNELS=("development","candidate","stable")
REAL_TRADING=False
def sha256_bytes(data): return hashlib.sha256(data).hexdigest()
def validate_manifest(m,current_version,channel="stable"):
    if channel not in CHANNELS:return {"ok":False,"reason":"INVALID_CHANNEL"}
    req=("version","channel","sha256","signature","package")
    if not isinstance(m,dict) or any(not m.get(k) for k in req):return {"ok":False,"reason":"INCOMPLETE_MANIFEST"}
    if m["channel"]!=channel:return {"ok":False,"reason":"WRONG_CHANNEL"}
    if m["version"]==current_version:return {"ok":False,"reason":"NO_UPDATE"}
    if m.get("real_trading") is not False:return {"ok":False,"reason":"UNSAFE_TRADING_STATE"}
    return {"ok":True,"reason":"CANDIDATE_ONLY","version":m["version"]}
def verify_package(data,manifest,signature_verified):
    if not signature_verified:return {"ok":False,"reason":"BAD_SIGNATURE"}
    if sha256_bytes(data)!=manifest.get("sha256"):return {"ok":False,"reason":"HASH_MISMATCH"}
    return {"ok":True,"reason":"VERIFIED"}
def update_plan(verified,health_after_restart,previous_version):
    if not verified:return {"action":"ABORT","rollback":False}
    if not health_after_restart:return {"action":"ROLLBACK","rollback":True,"target":previous_version}
    return {"action":"COMMIT","rollback":False}
