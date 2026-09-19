"""Launch adversarial matrix: dangerous uncertainty must fail closed."""
REAL_TRADING=False
SCENARIOS=("update_interrupted","corrupt_package","incompatible_version","offline","api_down",
"supabase_down","railway_down","duplicate_process","close_during_write","disk_full","bad_clock","unexpected_restart")
DANGEROUS={"corrupt_package","incompatible_version","supabase_down","railway_down","duplicate_process","close_during_write","disk_full","bad_clock","unexpected_restart"}
def disposition(scenario,recovered=False):
    if scenario not in SCENARIOS:return {"mode":"BLOCKED","paper_mutation":False,"reason":"UNKNOWN_SCENARIO"}
    if scenario in ("offline","api_down"):return {"mode":"READ_ONLY","paper_mutation":False,"reason":scenario.upper()}
    if recovered:return {"mode":"RECOVERY_REQUIRED","paper_mutation":False,"reason":"RECONCILE_BEFORE_RESUME"}
    return {"mode":"FAIL_CLOSED","paper_mutation":False,"reason":scenario.upper()}
