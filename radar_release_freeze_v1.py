"""Fail-closed freeze gate for the eventual Radar 1.6.0 candidate."""
from __future__ import annotations
REAL_TRADING=False

ACCEPTED_CODE_STATES={'VERIFIED','IMPLEMENTED','EXISTING_VERIFIED'}


def freeze_gate(task_states,release_integrity,*,required_runtime_days=30,observed_runtime_days=0):
    states=task_states or {};missing=[str(i) for i in range(1,71) if str(i) not in states]
    incomplete=[k for k,v in states.items() if str(v) not in ACCEPTED_CODE_STATES]
    integrity_ok=(release_integrity or {}).get('status')=='RELEASE_READY'
    runtime_ok=int(observed_runtime_days or 0)>=int(required_runtime_days)
    blockers=[]
    if missing:blockers.append('TASKS_UNMAPPED')
    if incomplete:blockers.append('TASKS_NOT_VERIFIED')
    if not integrity_ok:blockers.append('RELEASE_INTEGRITY')
    if not runtime_ok:blockers.append('RUNTIME_EVIDENCE')
    ready=not blockers
    return {'status':'FROZEN_1_6_0_CANDIDATE' if ready else 'NOT_FROZEN','candidate_version':'1.6.0' if ready else None,
            'missing_tasks':missing,'incomplete_tasks':incomplete,'observed_runtime_days':int(observed_runtime_days or 0),
            'required_runtime_days':int(required_runtime_days),'blockers':blockers,'setup_allowed':ready,
            'real_money_authorized':False,'can_trade':False,'real_trading':False}
