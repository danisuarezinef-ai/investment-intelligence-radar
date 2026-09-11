"""Pre-1.6 provenance hardening v5 for tasks 131-150.

This layer composes the stable v4 hardening runtime. New decision-time envelopes
captured transactionally are authoritative. Ledger-derived v4 envelopes remain a
clearly-labelled fallback only for trades that predate transactional capture.
Closed outcomes are linked to BUY envelopes using entry-known fields only.
"""
from __future__ import annotations

from collections import Counter

import radar_pre160_runtime_v3 as v3
import radar_pre160_runtime_v4 as v4
from radar_decision_provenance_v1 import load_local_envelopes
from radar_pre160_runtime_v4_linkage import regime_coverage_balance_safe

REAL_TRADING=False


def _ts(value):
    d=v4._dt(value);return d.isoformat() if d else str(value or '')


def _env_key(env):
    return (str(env.get('source_key') or ''),int(env.get('trade_id') or 0))


def _entry_key(competitor_key,symbol,entry_ts):
    return (str(competitor_key or ''),str(symbol or '').upper(),_ts(entry_ts))


def decision_envelope_candidates(capture_started_at):
    """Return exact local envelopes first and v4 fallback only for uncaptured trades."""
    exact=load_local_envelopes(capture_started_at)
    exact_keys={_env_key(x) for x in exact}
    fallback=[]
    for env in v4.decision_envelope_candidates(capture_started_at):
        if _env_key(env) in exact_keys:continue
        item=dict(env);p=dict(item.get('provenance') or {});p['capture_mode']='LEDGER_DERIVED_FALLBACK';p['strategy_version_status']='NOT_CAPTURED_AT_DECISION';p['lookahead']=False;p['backfilled']=False;p['reconstructed']=True;p['real_trading']=False;item['provenance']=p;item['real_trading']=False;fallback.append(item)
    rows=exact+fallback;rows.sort(key=lambda x:(str(x.get('trade_ts') or ''),str(x.get('source_key') or ''),int(x.get('trade_id') or 0)))
    return rows


def merged_envelopes(capture_started_at,remote_envelopes):
    """Remote frozen rows stay authoritative; add only not-yet-frozen local rows."""
    remote=[dict(x) for x in remote_envelopes or []];seen={_env_key(x) for x in remote};out=list(remote)
    for env in decision_envelope_candidates(capture_started_at):
        if _env_key(env) not in seen:out.append(env);seen.add(_env_key(env))
    out.sort(key=lambda x:(str(x.get('trade_ts') or ''),str(x.get('source_key') or ''),int(x.get('trade_id') or 0)))
    return out


def decision_trace_linkage(decisions,envelopes):
    """Audit entry->closed outcome trace without any exit field in the join key."""
    entry_index={}
    collisions=Counter()
    for env in envelopes or []:
        if str(env.get('side') or '').upper()!='BUY':continue
        key=_entry_key(env.get('competitor_key'),env.get('symbol'),env.get('trade_ts'))
        if key in entry_index:collisions[key]+=1
        else:entry_index[key]=env
    rows=[];missing=0;version_missing=0;lookahead_flags=0
    for d in v3._prospective(decisions):
        key=_entry_key(d.get('competitor_key'),d.get('symbol'),d.get('entry_ts'));env=entry_index.get(key)
        if env is None:missing+=1;continue
        provenance=env.get('provenance') if isinstance(env.get('provenance'),dict) else {}
        if not env.get('strategy_version'):version_missing+=1
        if provenance.get('lookahead') is True:lookahead_flags+=1
        rows.append({'competitor_key':d.get('competitor_key'),'symbol':d.get('symbol'),'entry_ts':_ts(d.get('entry_ts')),
                     'exit_ts':d.get('exit_ts'),'decision_fingerprint':d.get('decision_fingerprint'),'entry_envelope_hash':env.get('envelope_hash'),
                     'strategy_version':env.get('strategy_version'),'capture_mode':provenance.get('capture_mode'),
                     'regime':env.get('regime'),'provider_status':provenance.get('provider_status'),'benchmark_status':provenance.get('benchmark_status')})
    blockers=[]
    if missing:blockers.append('PROSPECTIVE_ENTRY_ENVELOPE_MISSING')
    if version_missing:blockers.append('PROSPECTIVE_STRATEGY_VERSION_MISSING')
    if lookahead_flags:blockers.append('LOOKAHEAD_FLAG_DETECTED')
    if collisions:blockers.append('AMBIGUOUS_ENTRY_ENVELOPE_KEY')
    if not rows:blockers.append('NO_LINKED_PROSPECTIVE_CLOSES')
    return {'status':'COMPLETE' if rows and not blockers else 'EVIDENCE_PENDING' if not lookahead_flags else 'FAILED',
            'prospective_closes':len(v3._prospective(decisions)),'matched':len(rows),'missing':missing,'strategy_versions_missing':version_missing,
            'lookahead_flags':lookahead_flags,'ambiguous_keys':len(collisions),'linkage':'competitor+symbol+entry_ts',
            'uses_exit_fields_for_entry_linkage':False,'rows':rows[:100],'blockers':blockers,'real_trading':False}


def build_hardening_snapshot_v5(*,evidence_v3,durable_eval,evidence_authority,forward_records,base_runtime):
    base=v4.build_hardening_snapshot(evidence_v3=evidence_v3,durable_eval=durable_eval,evidence_authority=evidence_authority,
                                     forward_records=forward_records,base_runtime=base_runtime)
    capture_started_at=(durable_eval or {}).get('capture_started_at');remote=(evidence_authority or {}).get('envelopes') or []
    local=decision_envelope_candidates(capture_started_at);envelopes=merged_envelopes(capture_started_at,remote);decisions=(durable_eval or {}).get('decisions') or []
    exact=sum(((x.get('provenance') or {}).get('capture_mode')=='AT_DECISION_TRANSACTION') for x in envelopes if isinstance(x,dict))
    fallback=sum(((x.get('provenance') or {}).get('capture_mode')=='LEDGER_DERIVED_FALLBACK') for x in envelopes if isinstance(x,dict))
    versions_missing=sum(1 for x in envelopes if not x.get('strategy_version'))
    provenance={'status':'COMPLETE' if envelopes and versions_missing==0 and fallback==0 else 'EVIDENCE_PENDING','envelopes':len(envelopes),
                'transactional_exact':exact,'ledger_fallback':fallback,'strategy_versions_missing':versions_missing,
                'blockers':(['DECISION_ENVELOPES_EMPTY'] if not envelopes else [])+(['STRATEGY_VERSION_NOT_CAPTURED_AT_DECISION'] if versions_missing else [])+
                           (['LEDGER_DERIVED_ENVELOPES_PRESENT'] if fallback else []),'real_trading':False}
    out=dict(base);out['status']='PRE160_EVIDENCE_V5';out['decision_envelope_provenance']=provenance
    out['regime_coverage']=regime_coverage_balance_safe(decisions,envelopes);out['decision_trace']=decision_trace_linkage(decisions,envelopes)
    out['envelopes_to_freeze']=local;out['envelope_source']={'remote_frozen':len(remote),'local_candidates':len(local),'transactional_exact':sum(((x.get('provenance') or {}).get('capture_mode')=='AT_DECISION_TRANSACTION') for x in local),'real_trading':False}
    out['setup_allowed']=False;out['automatic_release']=False;out['automatic_promotion']=False;out['automatic_demotion']=False;out['can_trade']=False;out['real_trading']=False
    out['snapshot_hash']=v4._hash({k:v for k,v in out.items() if k!='snapshot_hash'});return out