"""Continuous pre-1.6 integrity checks for PAPER/forward operation."""
from __future__ import annotations

from datetime import datetime,timezone

REAL_TRADING=False


def _f(x,default=None):
    try:return float(x)
    except (TypeError,ValueError):return default


def _dt(x):
    if not x:return None
    try:
        d=datetime.fromisoformat(str(x).replace('Z','+00:00'));return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:return None


def paper_account_integrity(status,tolerance=1e-6):
    s=status or {};cash=_f(s.get('cash'));invested=_f(s.get('invested'));total=_f(s.get('total'))
    blockers=[]
    if cash is None or invested is None or total is None:blockers.append('ACCOUNT_FIELDS_MISSING')
    elif abs((cash+invested)-total)>max(float(tolerance),abs(total)*1e-8):blockers.append('CASH_PLUS_INVESTED_MISMATCH')
    positions=s.get('positions') or []
    if any(_f(p.get('qty'),-1)<0 or _f(p.get('value'),-1)<0 for p in positions):blockers.append('NEGATIVE_POSITION')
    return {'status':'PASS' if not blockers else 'BLOCKED','blockers':blockers,'position_count':len(positions),
            'can_trade':False,'real_trading':False}


def forward_timestamp_audit(records):
    failures=[];valid=0
    for i,r in enumerate(records or []):
        created=_dt(r.get('created_at'));cutoff=_dt(r.get('data_cutoff'));known=_dt(r.get('known_at_boundary'));target=_dt(r.get('target_date'));evaluated=_dt(r.get('evaluated_at'))
        checks={'created':created is not None,'cutoff_not_future':bool(created and cutoff and cutoff<=created),
                'known_boundary_not_future':bool(created and known and known<=created),'target_after_prediction':bool(created and target and target>=created),
                'evaluation_after_target':evaluated is None or bool(target and evaluated>=target),'not_backfilled':r.get('backfilled') is not True}
        if all(checks.values()):valid+=1
        else:failures.append({'index':i,'prediction_hash':r.get('prediction_hash'),'checks':checks})
    return {'records':len(list(records or [])),'valid':valid,'failures':failures,'pass':valid>0 and not failures,
            'no_lookahead_verified':valid>0 and not failures,'real_trading':False}


def freshness_watch(timestamps,thresholds_seconds=None,now_value=None):
    thresholds={'market':900,'events':3600,'forward_sync':900,'paper_checkpoint':300,'league':300};thresholds.update(thresholds_seconds or {})
    now_dt=_dt(now_value) or datetime.now(timezone.utc);rows={};stale=[]
    for key,limit in thresholds.items():
        ts=_dt((timestamps or {}).get(key));age=(now_dt-ts).total_seconds() if ts else None
        status='UNKNOWN' if age is None else ('FRESH' if age<=float(limit) else 'STALE')
        rows[key]={'timestamp':str((timestamps or {}).get(key) or ''),'age_seconds':age,'threshold_seconds':limit,'status':status}
        if status!='FRESH':stale.append(key)
    return {'status':'FRESH' if not stale else 'DEGRADED','sources':rows,'stale_or_unknown':stale,'real_trading':False}


def shadow_champion_separation(*,shadow_can_trade=False,shadow_mutates_forward=False,champion_reads_shadow_results=False,
                               forward_predictions_immutable=True,research_writes_forward=False):
    checks={'shadow_cannot_trade':shadow_can_trade is False,'shadow_no_forward_mutation':shadow_mutates_forward is False,
            'champion_no_unapproved_shadow_dependency':champion_reads_shadow_results is False,
            'forward_predictions_immutable':forward_predictions_immutable is True,'research_does_not_write_forward':research_writes_forward is False}
    return {'status':'PASS' if all(checks.values()) else 'BLOCKED','checks':checks,'failed':[k for k,v in checks.items() if not v],
            'can_trade':False,'real_trading':False}


def corporate_currency_audit(*,symbols=None,corporate_action_known=None,currencies=None,fx_verified=None):
    symbols=list(symbols or []);ca=corporate_action_known or {};currencies=currencies or {};fx_verified=fx_verified or {}
    rows=[];blockers=[]
    for sym in symbols:
        currency=currencies.get(sym);ca_ok=ca.get(sym)
        fx_ok=True if currency in (None,'EUR') else fx_verified.get(currency) is True
        row={'symbol':sym,'corporate_actions_verified':ca_ok is True,'currency':currency,'fx_verified':fx_ok}
        rows.append(row)
        if ca_ok is not True:blockers.append(f'{sym}:CORPORATE_ACTIONS_UNKNOWN')
        if not fx_ok:blockers.append(f'{sym}:FX_UNKNOWN')
    return {'status':'PASS' if symbols and not blockers else ('INSUFFICIENT_EVIDENCE' if not symbols else 'BLOCKED'),
            'rows':rows,'blockers':blockers,'real_trading':False}


def release_integrity(*,ci=False,windows=False,smoke=False,cloud=False,persistence=False,forward=False,
                      paper_integrity=False,data_quality=False,identity=False,api_contract=False,real_trading=False):
    checks={'ci':bool(ci),'windows':bool(windows),'simulation_smoke':bool(smoke),'cloud':bool(cloud),'persistence':bool(persistence),
            'forward_integrity':bool(forward),'paper_integrity':bool(paper_integrity),'data_quality':bool(data_quality),
            'version_identity':bool(identity),'api_contract':bool(api_contract),'real_trading_off':real_trading is False}
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'RELEASE_READY' if not blockers else 'BLOCKED','checks':checks,'blockers':blockers,
            'candidate':'1.6.0' if not blockers else None,'real_trading':False}
