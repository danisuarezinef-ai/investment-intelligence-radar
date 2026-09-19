"""RC gate for the first Android Radar PAPER release."""
REAL_TRADING=False
REQUIRED=("unit_tests","ci","apk_or_aab_built","signature","hash","clean_install","upgrade_test",
"launch_test","background_resume","process_death_restore","device_reboot_restore","offline_read_only",
"cloud_recovery","smoke_test","rollback_or_safe_update_recovery","real_trading_false")
def rc_gate(evidence):
    evidence=evidence if isinstance(evidence,dict) else {}
    missing=[k for k in REQUIRED if evidence.get(k) is not True]
    return {"pass":not missing,"missing":missing,"status":"PASS" if not missing else "NOT_VERIFIED"}
