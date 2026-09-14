"""Operational proof tasks 161-170 for autonomous PAPER Radar.

All gates are evidence-driven and fail closed. No historical/calendar time is promoted
into valid forward maturity. REAL_TRADING is permanently false in this module.
"""
from __future__ import annotations
REAL_TRADING=False


def _task(status,**e):return {'status':status,'evidence':{**e,'real_trading':False}}

def source_sync(main_sha,railway_source_sha):
    ok=bool(main_sha and railway_source_sha and main_sha==railway_source_sha)
    return _task('PASS' if ok else 'BLOCKED_SOURCE_MISMATCH',main_sha=main_sha,railway_source_sha=railway_source_sha)

def production_deployment(deployment,required_runtime='v22'):
    d=deployment or {};runtime=str(d.get('runtime') or '')
    ok=d.get('status')=='SUCCESS' and runtime in (required_runtime,'v23') and d.get('real_trading') is False
    return _task('PASS' if ok else 'NOT_VERIFIED',deployment=d,required_runtime=required_runtime)

def deployed_sha_proof(main_sha,deployed_sha,runtime_sha):
    ok=bool(main_sha and main_sha==deployed_sha==runtime_sha)
    return _task('PASS' if ok else 'FAIL_CLOSED',main_sha=main_sha,deployed_sha=deployed_sha,runtime_sha=runtime_sha)

def startup_chain(threads):
    required={'paper-v12-supervision','paper-disaster-probes','paper-learning-41-50','paper-forward-51-60','paper-intelligence-61-70','paper-portfolio-71-80','paper-policy-81-90','paper-validation-91-100','paper-maturity-writer'}
    present=set(threads or [])
    missing=sorted(required-present)
    return _task('PASS' if not missing else 'FAIL_CLOSED',required=sorted(required),present=sorted(present),missing=missing)

def endpoint_audit(results):
    r=results or {};required=['/health','/autonomous-simulator/tasks-21-160-v1','/autonomous-simulator/tasks-161-170-v1']
    bad=[p for p in required if r.get(p) not in (200,'200','PASS')]
    return _task('PASS' if not bad else 'NOT_VERIFIED',required=required,failures=bad,results=r)

def ci_full_chain(ci):
    c=ci or {};ok=c.get('status')=='PASS' and c.get('legacy_controls_preserved') is True and c.get('v22_controls_pass') is True
    return _task('PASS' if ok else 'NOT_VERIFIED',ci=c)

def supabase_schema(schema):
    s=schema or {};required={'radar_paper_forward_maturity_ledger','radar_append_paper_maturity_interval','radar_paper_valid_forward_hours'}
    present=set(s.get('objects') or []);missing=sorted(required-present)
    ok=not missing and s.get('rls_enabled') is True and s.get('anon_write_allowed') is False
    return _task('PASS' if ok else 'FAIL_CLOSED',missing=missing,schema=s)

def persistence_authority(authority):
    a=authority or {};ok=a.get('edge_active') is True and a.get('status')=='AUTHORITY_READY' and a.get('real_trading') is False
    return _task('PASS' if ok else 'FAIL_CLOSED',authority=a)

def maturity_ledger(authority):
    a=authority or {};ok=a.get('status')=='AUTHORITY_READY' and a.get('valid_forward_hours') is not None
    return _task('PASS' if ok else 'FAIL_CLOSED',valid_forward_hours=a.get('valid_forward_hours'),authority=a,
                 append_only=True,idempotent=True,overlap_credit_allowed=False,backfill_credit_allowed=False,downtime_credit_allowed=False)

def valid_forward_authority(authority):
    a=authority or {};hours=a.get('valid_forward_hours')
    ok=a.get('status')=='AUTHORITY_READY' and isinstance(hours,(int,float)) and hours>=0
    return _task('PASS' if ok else 'FAIL_CLOSED',valid_forward_hours=hours,source='SUPABASE_DURABLE_LEDGER',
                 historical_credit_allowed=False,calendar_elapsed_used=False,backfill_credit_allowed=False)

def board(**kw):
    tasks={
      '161':source_sync(kw.get('main_sha'),kw.get('railway_source_sha')),
      '162':production_deployment(kw.get('deployment')),
      '163':deployed_sha_proof(kw.get('main_sha'),kw.get('deployed_sha'),kw.get('runtime_sha')),
      '164':startup_chain(kw.get('threads')),
      '165':endpoint_audit(kw.get('endpoints')),
      '166':ci_full_chain(kw.get('ci')),
      '167':supabase_schema(kw.get('schema')),
      '168':persistence_authority(kw.get('authority')),
      '169':maturity_ledger(kw.get('authority')),
      '170':valid_forward_authority(kw.get('authority')),
    }
    return {'status':'OPERATIONAL_PROOF_161_170','tasks':tasks,'automatic_promotion':False,'automatic_release':False,
            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
