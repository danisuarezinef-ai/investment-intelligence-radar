"""Fail-closed SIMULATION READY v1 gate."""
from __future__ import annotations

import importlib

REAL_TRADING = False
REQUIRED_MODULES = (
    "radar_learning",
    "radar_learning_guarded",
    "radar_historical_lab",
    "radar_benchmark",
    "radar_simulation_factory",
)


def audit_simulation_ready():
    checks=[]
    for name in REQUIRED_MODULES:
        try:
            mod=importlib.import_module(name)
            checks.append({"check":"module:"+name,"status":"PASS"})
            if getattr(mod,"REAL_TRADING",False):
                checks.append({"check":"real_trading:"+name,"status":"FAIL","detail":"REAL_TRADING enabled"})
        except Exception as exc:
            checks.append({"check":"module:"+name,"status":"FAIL","detail":str(exc)[:300]})
    # Epistemic gates are explicit. UNKNOWN is not silently treated as PASS.
    required_evidence={
        "point_in_time_data":"NOT_VERIFIED",
        "survivorship_controls":"NOT_VERIFIED",
        "corporate_actions":"NOT_VERIFIED",
        "delisting_returns":"NOT_VERIFIED",
        "transaction_costs":"NOT_VERIFIED",
        "fx_costs":"NOT_VERIFIED",
        "purged_temporal_validation":"IMPLEMENTED_NOT_REVERIFIED",
        "forward_immutable_evidence":"NOT_ACTIVE_IN_PRODUCTION",
    }
    for key,value in required_evidence.items():
        checks.append({"check":key,"status":"PASS" if value=="VERIFIED" else "BLOCKED","detail":value})
    failed=[x for x in checks if x["status"] in ("FAIL","BLOCKED")]
    return {"simulation_ready":not failed,"checks":checks,"blocking":failed,"real_trading":False}
