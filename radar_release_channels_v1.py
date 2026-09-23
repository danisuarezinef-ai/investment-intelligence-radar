"""Promotion gates for internal Radar update channels."""
REAL_TRADING=False
CHANNELS=("development","candidate","stable")
def promotion_gate(source,target,evidence):
    evidence=evidence if isinstance(evidence,dict) else {}
    if source not in CHANNELS or target not in CHANNELS:return {"allowed":False,"reason":"INVALID_CHANNEL"}
    if target=="candidate":
        needed=("tests_green","ci_green","real_trading_false")
    elif target=="stable":
        needed=("tests_green","ci_green","clean_install","upgrade_previous","launch_ok","restore_ok","smoke_ok","rollback_tested","real_trading_false")
    else:
        return {"allowed":False,"reason":"NO_BACK_PROMOTION"}
    missing=[k for k in needed if evidence.get(k) is not True]
    return {"allowed":not missing,"reason":"READY" if not missing else "MISSING_EVIDENCE","missing":missing}
