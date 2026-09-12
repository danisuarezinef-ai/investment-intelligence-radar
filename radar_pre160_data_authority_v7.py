"""Point-in-time data authority and lineage controls for tasks 221-240."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

REAL_TRADING = False
STATES = frozenset({'PASS', 'PENDING_SAMPLE', 'PENDING_TIME', 'NOT_VERIFIED', 'FAILED'})


def _task(i, state, detail, *, critical=False, evidence=None):
    if state not in STATES:
        raise ValueError(state)
    out={'task':int(i),'state':state,'detail':str(detail),'critical':bool(critical)}
    if evidence is not None: out['evidence']=evidence
    return out


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def normalize_utc(value: str) -> str:
    dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if dt.tzinfo is None:
        raise ValueError('naive timestamp is forbidden')
    return dt.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def decision_fingerprint(*, data_hash: str, feature_hash: str, model_hash: str, strategy_hash: str, context_hash: str) -> str:
    return content_hash({'data':data_hash,'features':feature_hash,'model':model_hash,'strategy':strategy_hash,'context':context_hash})


def dedupe_predictions(rows: list[dict]) -> dict:
    seen={}; collisions=[]
    for row in rows or []:
        key=(row.get('symbol'),row.get('decision_ts'),row.get('horizon'),row.get('model_version'))
        fp=content_hash(row)
        if key in seen and seen[key] != fp:
            collisions.append({'key':key,'first':seen[key],'second':fp})
        else:
            seen[key]=fp
    return {'unique_keys':len(seen),'collisions':collisions,'pass':not collisions,'real_trading':False}


def bad_tick_filter(prices: list[float], *, max_jump_pct=40.0) -> dict:
    clean=[]; rejected=[]; prev=None
    for raw in prices or []:
        try: p=float(raw)
        except (TypeError,ValueError): rejected.append(raw); continue
        if p <= 0: rejected.append(raw); continue
        if prev is not None and abs(p/prev-1.0)*100 > float(max_jump_pct):
            rejected.append(raw); continue
        clean.append(p); prev=p
    return {'clean':clean,'rejected':rejected,'filter_is_non_destructive':True,'real_trading':False}


def deterministic_replay(original: dict, replayed: dict) -> dict:
    a=content_hash(original); b=content_hash(replayed)
    return {'status':'PASS' if a==b else 'FAILED','original_hash':a,'replay_hash':b,'equal':a==b,'real_trading':False}


def build_data_authority_tasks(*, evidence: dict, hardening: dict, runtime: dict, metadata: dict | None = None) -> dict:
    evidence=evidence or {}; hardening=hardening or {}; runtime=runtime or {}; m=metadata or {}
    tasks={}

    ledger_authorities=m.get('forward_ledger_authorities') or []
    tasks[221]=_task(221,'PASS' if len(ledger_authorities)==1 else ('FAILED' if len(ledger_authorities)>1 else 'NOT_VERIFIED'),
                     'exactly one canonical forward ledger authority',critical=True,evidence={'authorities':ledger_authorities})

    d=dedupe_predictions(m.get('prediction_samples') or [])
    tasks[222]=_task(222,'PASS' if d['pass'] and d['unique_keys']>0 else ('FAILED' if not d['pass'] else 'PENDING_SAMPLE'),
                     'decision-state prediction deduplication',critical=True,evidence={'unique_keys':d['unique_keys'],'collisions':len(d['collisions'])})
    tasks[223]=_task(223,'PASS' if m.get('pit_universe_frozen') is True else 'NOT_VERIFIED','point-in-time investable universe freeze',critical=True)
    tasks[224]=_task(224,'PASS' if m.get('survivorship_guard') is True else 'NOT_VERIFIED','survivorship-bias guard')
    tasks[225]=_task(225,'PASS' if m.get('corporate_actions_authority') is True else 'NOT_VERIFIED','corporate actions authority: splits/dividends/mergers/delistings')
    tasks[226]=_task(226,'PASS' if m.get('price_field_policy') else 'NOT_VERIFIED','entry/valuation/exit price-field authority',critical=True,evidence=m.get('price_field_policy'))
    tasks[227]=_task(227,'PASS' if m.get('market_calendar_authority') is True else 'NOT_VERIFIED','market-calendar authority')

    ts_samples=m.get('timestamp_samples') or []
    normalized=True
    for ts in ts_samples:
        try: normalize_utc(ts)
        except Exception: normalized=False; break
    tasks[228]=_task(228,'PASS' if ts_samples and normalized else ('FAILED' if ts_samples and not normalized else 'PENDING_SAMPLE'),
                     'timezone normalization to aware UTC',critical=True)

    taxonomy=set(m.get('missing_data_taxonomy') or [])
    needed={'LEGITIMATE_ABSENCE','PROVIDER_FAILURE','STALE','DELAYED'}
    tasks[229]=_task(229,'PASS' if needed.issubset(taxonomy) else 'NOT_VERIFIED','missing-data taxonomy distinguishes absence/failure/stale/delayed')
    freshness=evidence.get('freshness') or {}
    tasks[230]=_task(230,'PASS' if freshness.get('status')=='FRESH' and m.get('freshness_sla_by_type') else ('FAILED' if freshness.get('status')=='DEGRADED' else 'NOT_VERIFIED'),
                     'data freshness SLA by data type',critical=True)
    tasks[231]=_task(231,'PASS' if int(m.get('cross_provider_pairs') or 0)>0 else 'PENDING_SAMPLE','critical prices cross-checked across providers')
    div=int(m.get('provider_divergence_violations') or 0)
    pairs=int(m.get('cross_provider_pairs') or 0)
    tasks[232]=_task(232,'FAILED' if div else ('PASS' if pairs else 'PENDING_SAMPLE'),'provider divergence alarm',critical=True,evidence={'pairs':pairs,'violations':div})

    ticks=m.get('price_samples') or []
    filtered=bad_tick_filter(ticks) if ticks else {'rejected':[],'clean':[]}
    tasks[233]=_task(233,'PASS' if ticks else 'PENDING_SAMPLE','non-destructive bad-tick filter',evidence={'rejected':len(filtered.get('rejected') or [])})
    tasks[234]=_task(234,'PASS' if m.get('immutable_raw_vault') is True else 'NOT_VERIFIED','immutable raw-data vault',critical=True)

    hashes={
        'dataset':m.get('dataset_hash'), 'features':m.get('feature_hash'), 'model':m.get('model_hash'),
        'strategy':m.get('strategy_hash'), 'context':m.get('context_hash')
    }
    tasks[235]=_task(235,'PASS' if hashes['dataset'] else 'PENDING_SAMPLE','dataset lineage to immutable source',critical=True)
    tasks[236]=_task(236,'PASS' if hashes['features'] else 'PENDING_SAMPLE','feature lineage to dataset inputs')
    tasks[237]=_task(237,'PASS' if hashes['model'] and hashes['strategy'] else 'PENDING_SAMPLE','model/version/parameter lineage',critical=True)
    complete=all(hashes.values())
    fp=decision_fingerprint(data_hash=hashes['dataset'],feature_hash=hashes['features'],model_hash=hashes['model'],strategy_hash=hashes['strategy'],context_hash=hashes['context']) if complete else None
    tasks[238]=_task(238,'PASS' if fp else 'PENDING_SAMPLE','decision fingerprint binds data+features+model+strategy+context',critical=True,evidence={'fingerprint':fp})

    replay=m.get('deterministic_replay') or {}
    if replay.get('original') is not None and replay.get('replayed') is not None:
        rep=deterministic_replay(replay['original'],replay['replayed']); s239=rep['status']
    else:
        rep={}; s239='PENDING_SAMPLE'
    tasks[239]=_task(239,s239,'deterministic historical decision replay',critical=True,evidence=rep or None)

    trace=hardening.get('decision_trace') or {}
    lookahead=int(trace.get('lookahead_flags') or 0)
    exit_fields=trace.get('uses_exit_fields_for_entry_linkage')
    if lookahead or exit_fields is True: s240='FAILED'
    elif 'lookahead_flags' in trace and exit_fields is False: s240='PASS'
    else: s240='PENDING_SAMPLE'
    tasks[240]=_task(240,s240,'automatic lookahead audit for every new feature/decision linkage',critical=True,
                     evidence={'lookahead_flags':lookahead,'uses_exit_fields':exit_fields})

    return {'status':'PRE160_DATA_AUTHORITY_V7','tasks':{str(k):v for k,v in tasks.items()},
            'decision_fingerprint':fp,'automatic_release':False,'automatic_promotion':False,'can_trade':False,'real_trading':False}
