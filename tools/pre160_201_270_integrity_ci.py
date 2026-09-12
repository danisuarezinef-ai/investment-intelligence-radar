"""Static integrity gate for pre-1.6 tasks 201-270."""
from pathlib import Path
import json

def audit(root='.'):
    root=Path(root);findings=[]
    required=(
        'PRE160_TASKS_201_270.md','radar_pre160_resilience_v7.py','radar_pre160_data_authority_v7.py',
        'radar_pre160_statistics_v7.py','radar_pre160_autonomy_v7.py','radar_pre160_controls_v7.py',
        'radar_market_data_authority_v1.py','radar_provider_resilience_v1.py','radar_raw_vault_v1.py','radar_sync_queue_v2.py',
        'radar_pre160_cache_v7.py','cloud_service_v7.py','tests/test_pre160_tasks_201_270.py','tests/test_pre160_cache_v7.py')
    for p in required:
        if not (root/p).exists():findings.append('MISSING_201_270_COMPONENT:'+p)
    start=(root/'start.sh').read_text(encoding='utf-8-sig')
    v7=(root/'cloud_service_v7.py').read_text(encoding='utf-8-sig') if (root/'cloud_service_v7.py').exists() else ''
    if 'cloud_service_v7.py' not in start:findings.append('START_NOT_V7')
    if 'import cloud_service_v6 as base6' not in v7 or 'base6.start_runtime()' not in v7:findings.append('V7_NOT_COMPOSED_OVER_V6')
    for endpoint in ('/pre160-audit-201-270-v1','/pre160-resilience-v7','/pre160-data-authority-v7','/pre160-statistical-validity-v7','/pre160-autonomy-v7','/pre160-master-gate-v3','/pre160-cache-v7'):
        if endpoint not in v7:findings.append('MISSING_V7_ENDPOINT:'+endpoint)
    for p,tokens in {
        'radar_pre160_resilience_v7.py':('classify_retry','COLD_ENDPOINT_BUDGET_MS','ROUNDTRIP_BUDGET_MS','automatic_release'),
        'radar_pre160_data_authority_v7.py':('decision_fingerprint','dedupe_predictions','deterministic_replay','uses_exit_fields_for_entry_linkage'),
        'radar_pre160_statistics_v7.py':('effective_sample_size','calibration_metrics','benjamini_hochberg','deflated_score'),
        'radar_pre160_autonomy_v7.py':('challenger_incubation','degradation_detector','shadow_ensemble','abstention_decision','manual_review_only'),
        'radar_sync_queue_v2.py':('dead_letter','ack_after_remote_success','MAX_ATTEMPTS'),
        'radar_pre160_cache_v7.py':('stale_while_revalidate','dependency_keys','prewarm_enabled'),
        'radar_market_data_authority_v1.py':('survivorship_guard','corporate_actions','PRICE_FIELD_POLICY','MISSING_DATA_KINDS'),
        'radar_provider_resilience_v1.py':('ProviderBulkheads','reconciliation_contract','bulkhead_isolation','reconcile_after_recovery'),
        'radar_raw_vault_v1.py':('append_only','SHA-256','overwrite_allowed'),
    }.items():
        text=(root/p).read_text(encoding='utf-8-sig') if (root/p).exists() else ''
        for token in tokens:
            if token not in text:findings.append('INCOMPLETE_'+p+':'+token)
    controls=(root/'radar_pre160_controls_v7.py').read_text(encoding='utf-8-sig') if (root/'radar_pre160_controls_v7.py').exists() else ''
    compact=controls.replace(' ','')
    for token in ('range(201,271)','stable_windows_version','automatic_release','live_execution_allowed','REAL_TRADING=False','reconciliation_contract'):
        if token not in compact:findings.append('V7_MATRIX_INCOMPLETE:'+token)
    version=json.loads((root/'version.json').read_text(encoding='utf-8-sig')).get('version')
    if version!='1.5.28':findings.append('UNEXPECTED_WINDOWS_VERSION_BUMP')
    if 'REAL_TRADING=False' not in v7.replace(' ',''):findings.append('V7_TRADING_BOUNDARY_MISSING')
    return {'status':'PASS' if not findings else 'FAIL','findings':findings,'version':version,'setup_built':False,'real_trading':False}

if __name__=='__main__':
    out=audit();print(json.dumps(out,indent=2));raise SystemExit(0 if out['status']=='PASS' else 1)
