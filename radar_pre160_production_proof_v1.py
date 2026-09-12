"""Content-addressed external production-proof verifier for pre-1.6.

The proof JSON is the only excluded artifact. All runtime/governance code that can
change the audited conclusion is inside the protected digest. This module never
creates or self-approves proof.
"""
from __future__ import annotations
import hashlib,json
from pathlib import Path

REAL_TRADING=False
DEFAULT_PROOF_PATH='PRE160_PRODUCTION_PROOF.json'
PROTECTED_PATHS=(
 'version.json','start.sh','cloud_service_v3.py','cloud_service_v4.py','cloud_service_v5.py','cloud_service_v6.py','cloud_service_v7.py','cloud_service_v8.py','cloud_service_v9.py',
 'radar_supabase_sync.py','radar_supabase_sync_partitioned_v2.py','radar_learning_sync.py','radar_forward_outcome_sync_v1.py','radar_closed_loop_runtime_v1.py','radar_champion_challenger_v1.py','radar_learning_engine_v3.py','radar_validation_runtime_v3.py','radar_operational_health_v2.py',
 'radar_forward_evidence_v2.py','radar_brain_calibration_v2.py','radar_brain_competition_v3.py','radar_brain_readiness_v1.py','radar_brain_persistence_v1.py','radar_autonomous_simulator_v1.py','radar_autonomy_e2e_v1.py','radar_autonomous_paper_control_v1.py','radar_autonomous_learning_16_40_v1.py','radar_autonomous_learning_41_60_v1.py','radar_ceo_handoff_v1.py',
 'radar_pre160_cloud_v3.py','radar_pre160_cloud_v4.py','radar_pre160_runtime_v3.py','radar_pre160_runtime_v4.py','radar_pre160_runtime_v4_linkage.py','radar_pre160_runtime_v5.py',
 'radar_pre160_controls_v6.py','radar_pre160_controls_v7.py','radar_pre160_controls_v8.py','radar_pre160_resilience_v7.py','radar_pre160_data_authority_v7.py','radar_pre160_statistics_v7.py','radar_pre160_autonomy_v7.py','radar_pre160_cache_v7.py','radar_pre160_readiness_v4.py',
 'radar_market_data_authority_v1.py','radar_provider_resilience_v1.py','radar_provider_resilience_v2.py','radar_raw_vault_v1.py','radar_sync_queue_v2.py','radar_sync_queue_v3.py',
 'radar_pre160_recovery_v2.py','radar_pre160_release_authority_v2.py','radar_pre160_production_proof_v1.py','radar_pre160_production_proof_v3.py','radar_pre160_persistence_v1.py','radar_pre160_evidence_persistence_v1.py','radar_pre160_hardening_persistence_v1.py',
 'radar_paper_engine_persistence_v1.py','radar_agents.py','radar_champion_portfolio.py','radar_causal_scoring_v2.py','radar_promotion_governance_v2.py',
 'supabase/functions/radar-sync/index.ts','supabase/functions/radar-learning-sync/index.ts','supabase/functions/radar-retry-queue/index.ts','supabase/functions/radar-brain-evidence/index.ts','supabase/functions/radar-paper-engine-checkpoint/index.ts','supabase/functions/radar-pre160-evidence/index.ts','supabase/functions/radar-pre160-hardening/index.ts',
 'supabase/migrations/20260912093000_pre160_remote_retry_queue_v3.sql','supabase/migrations/20260912110000_pre160_brain_evidence_snapshots_v1.sql',
 '.github/workflows/pre160-hardening-production-audit.yml','.github/workflows/pre160-201-270-production-audit.yml','.github/workflows/pre160-271-310-production-audit.yml','.github/workflows/pre160-311-370-production-audit.yml','.github/workflows/autonomous-paper-production-audit.yml','.github/workflows/integration-ci.yml',
 'tools/pre160_integrity_ci.py','tools/pre160_201_270_integrity_ci.py','tools/pre160_271_310_integrity_ci.py','tools/pre160_311_370_integrity_ci.py','tools/pre160_repo_audit_v2.py','tools/autonomous_learning_16_40_integrity_ci.py','tools/autonomous_learning_41_60_integrity_ci.py','PRE160_LEGACY_PR_RECONCILIATION.md','PRE160_TASKS_311_370.md',
)

def protected_digest(root='.',paths=PROTECTED_PATHS):
    root=Path(root);h=hashlib.sha256();missing=[];ordered=tuple(sorted(str(x) for x in paths))
    for rel in ordered:
        p=root/rel
        if not p.exists() or not p.is_file():missing.append(rel);continue
        raw=p.read_bytes();h.update(rel.encode());h.update(b'\0');h.update(hashlib.sha256(raw).digest());h.update(b'\0')
    return {'digest':h.hexdigest() if not missing else None,'missing':missing,'files':len(ordered),'algorithm':'SHA-256','proof_json_excluded':DEFAULT_PROOF_PATH not in ordered}

def production_proof_status(root='.',proof_path=DEFAULT_PROOF_PATH,paths=PROTECTED_PATHS):
    current=protected_digest(root,paths);path=Path(root)/proof_path
    if current['missing']:
        return {'status':'FAILED','verified':False,'reason':'PROTECTED_FILES_MISSING','missing':current['missing'],'protected_files':current['files'],'real_trading':False}
    if not path.exists():
        return {'status':'NOT_VERIFIED','verified':False,'reason':'EXTERNAL_PRODUCTION_PROOF_NOT_RECORDED','protected_digest':current['digest'],'protected_files':current['files'],'digest_algorithm':current['algorithm'],'proof_json_excluded':current['proof_json_excluded'],'setup_allowed':False,'can_trade':False,'real_trading':False}
    try:proof=json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception as exc:return {'status':'FAILED','verified':False,'reason':'INVALID_PROOF_JSON','error':str(exc)[:300],'real_trading':False}
    checks={
      'digest_match':proof.get('protected_digest')==current['digest'],
      'ci_success':proof.get('audit_conclusion')=='success',
      'tasks_151_200_verified':proof.get('tasks_151_200_verified') is True,
      'tasks_201_270_verified':proof.get('tasks_201_270_verified') is True,
      'dual_sync_slo_verified':proof.get('dual_sync_slo_verified') is True,
      'windows_stable':proof.get('stable_windows_version')=='1.5.28',
      'real_trading_false':proof.get('real_trading') is False,
      'audit_run_recorded':proof.get('audit_run_id') not in (None,''),
      'audited_commit_recorded':bool(str(proof.get('audited_commit_sha') or '').strip()),
    }
    verified=all(checks.values())
    return {'status':'PASS' if verified else 'FAILED','verified':verified,'protected_digest':current['digest'],'protected_files':current['files'],'digest_algorithm':current['algorithm'],'checks':checks,'audit_run_id':proof.get('audit_run_id'),'audited_commit_sha':proof.get('audited_commit_sha'),'recorded_at':proof.get('recorded_at'),'proof_is_content_addressed':True,'proof_file_excluded_from_digest':True,'self_verifier_is_protected':'radar_pre160_production_proof_v1.py' in tuple(paths),'setup_allowed':False,'can_trade':False,'real_trading':False}
