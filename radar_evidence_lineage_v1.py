"""Prospective evidence lineage validator.

Every forward decision must be attributable to a model/version, data cutoff and source set.
"""
REAL_TRADING=False

REQUIRED=('decision_id','model_version','created_at','target_date','data_cutoff')


def validate_lineage(record):
    r=record or {}; blockers=[]
    for key in REQUIRED:
        if r.get(key) in (None,''): blockers.append('MISSING_'+key.upper())
    sources=r.get('sources')
    if not isinstance(sources,(list,tuple)) or not sources: blockers.append('MISSING_SOURCES')
    if r.get('backfilled') is True: blockers.append('BACKFILL_FORBIDDEN')
    created=str(r.get('created_at') or '')
    cutoff=str(r.get('data_cutoff') or '')
    target=str(r.get('target_date') or '')
    if created and cutoff and cutoff>created: blockers.append('FUTURE_DATA_CUTOFF')
    if created and target and created>target: blockers.append('CREATED_AFTER_TARGET')
    return {'status':'PASS' if not blockers else 'BLOCKED','blockers':blockers,'lineage_complete':not blockers,'real_trading':False}
