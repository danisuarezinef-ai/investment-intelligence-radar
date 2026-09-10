"""Fail-closed integrity audit for persisted forward decisions.

The auditor never repairs, reconstructs or backfills records. It only reports
violations so the forward evidence authority can remain prospective.
REAL_TRADING remains disabled.
"""
from datetime import datetime

REAL_TRADING=False
_REQUIRED=('origin_node','origin_id','created_at','symbol','horizon','target_date','model_version','prediction_hash','decision_state','data_cutoff','known_at_boundary')


def _dt(value):
    if isinstance(value,datetime):return value
    if value in (None,''):return None
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00'))
    except Exception:return None


def _flagged(record,key):
    for source in (record,record.get('payload') or {},record.get('outcome') or {},record.get('provenance_snapshot') or {}):
        if isinstance(source,dict) and source.get(key) is True:return True
    return False


def audit_forward_records(records):
    records=list(records or [])
    authority_seen=set();hash_seen=set();duplicate_authority=[];duplicate_hash=[];incomplete=[];timestamp_errors=[];backfill=[];lookahead=[]
    for index,row in enumerate(records):
        missing=[k for k in _REQUIRED if row.get(k) in (None,'')]
        if missing:incomplete.append({'index':index,'missing':missing})
        authority=(str(row.get('origin_node') or ''),str(row.get('origin_id') or ''))
        if all(authority):
            if authority in authority_seen:duplicate_authority.append({'index':index,'key':authority})
            authority_seen.add(authority)
        ph=str(row.get('prediction_hash') or '')
        if ph:
            if ph in hash_seen:duplicate_hash.append({'index':index,'prediction_hash':ph})
            hash_seen.add(ph)
        created=_dt(row.get('created_at'));target=_dt(row.get('target_date'));cutoff=_dt(row.get('data_cutoff'));boundary=_dt(row.get('known_at_boundary'));evaluated=_dt(row.get('evaluated_at'))
        errors=[]
        for name,value in (('created_at',created),('target_date',target),('data_cutoff',cutoff),('known_at_boundary',boundary)):
            if row.get(name) not in (None,'') and value is None:errors.append(name+'_invalid')
        if created and target and target<=created:errors.append('target_not_after_creation')
        if created and cutoff and cutoff>created:errors.append('cutoff_after_creation')
        if created and boundary and boundary>created:errors.append('boundary_after_creation')
        if target and evaluated and evaluated<target:errors.append('evaluated_before_target')
        if errors:timestamp_errors.append({'index':index,'errors':errors})
        if _flagged(row,'backfilled'):backfill.append(index)
        if _flagged(row,'lookahead'):lookahead.append(index)
    violations=(len(duplicate_authority)+len(duplicate_hash)+len(incomplete)+len(timestamp_errors)+len(backfill)+len(lookahead))
    return {
        'status':'PASS' if violations==0 else 'FAIL_CLOSED',
        'rows':len(records),'violations':violations,
        'duplicate_authority':duplicate_authority,'duplicate_hash':duplicate_hash,
        'incomplete':incomplete,'timestamp_errors':timestamp_errors,
        'backfill_contamination':backfill,'lookahead_contamination':lookahead,
        'repair_performed':False,'backfill_performed':False,'real_trading':REAL_TRADING,
    }
