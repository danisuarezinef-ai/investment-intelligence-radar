"""Pre-launch security invariants for PAPER-only Radar."""
from __future__ import annotations
REAL_TRADING=False
SECRET_MARKERS=("TOKEN","SECRET","PASSWORD","API_KEY","SUPABASE_KEY")
def runtime_security(config):
    config=config if isinstance(config,dict) else {}
    failures=[]
    if config.get("REAL_TRADING") not in (False,"false","False","0",0):failures.append("REAL_TRADING_NOT_FALSE")
    if config.get("broker_execution_enabled") is True:failures.append("BROKER_EXECUTION_ENABLED")
    if config.get("auto_promotion") is True:failures.append("AUTO_PROMOTION_ENABLED")
    if config.get("payments_enabled") is True:failures.append("PAYMENTS_ENABLED")
    return {"ok":not failures,"failures":failures,"mode":"PAPER"}
def redact(mapping):
    out={}
    for k,v in (mapping or {}).items():
        out[k]="[REDACTED]" if any(x in str(k).upper() for x in SECRET_MARKERS) else v
    return out
def release_security_gate(code_safe,runtime_safe,package_signed,package_hash_ok,updater_safe):
    checks={"code_safe":code_safe,"runtime_safe":runtime_safe,"package_signed":package_signed,
            "package_hash_ok":package_hash_ok,"updater_safe":updater_safe}
    missing=[k for k,v in checks.items() if v is not True]
    return {"allowed":not missing,"missing":missing,"real_trading":False}
