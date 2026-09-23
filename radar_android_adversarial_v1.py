"""Android-specific launch failure matrix."""
REAL_TRADING=False
SCENARIOS=("background_kill","process_death","device_reboot","network_loss","network_switch",
"cloud_down","api_timeout","update_interrupted","corrupt_update","signature_failure","low_storage",
"clock_skew","duplicate_session","old_app_version")
def disposition(s):
    if s not in SCENARIOS:return {"mode":"BLOCKED","paper_mutation":False}
    if s in ("network_loss","network_switch","cloud_down","api_timeout"):return {"mode":"READ_ONLY","paper_mutation":False}
    return {"mode":"FAIL_CLOSED","paper_mutation":False}
