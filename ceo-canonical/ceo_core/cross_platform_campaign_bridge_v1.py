from __future__ import annotations
from typing import Any


def qualify_cross_platform_campaign_bridge_v1(android_bundle:dict[str,Any],windows_campaign:dict[str,Any])->dict[str,Any]:
    problems=[]
    if android_bundle.get('ok') is not True: problems.append('android_evidence_incomplete')
    if windows_campaign.get('mode')!='plan_only': problems.append('windows_campaign_not_plan_only')
    if windows_campaign.get('automatic_installation') is not False: problems.append('automatic_installation_enabled')
    if windows_campaign.get('automatic_publication') is not False: problems.append('automatic_publication_enabled')
    if windows_campaign.get('requires_explicit_human_start') is not True: problems.append('human_start_not_required')
    gates=windows_campaign.get('physical_gates') or []
    if not gates or any(g.get('status')!='NOT_VERIFIED' for g in gates): problems.append('windows_physical_gate_preverified')
    ok=not problems
    return {'schema_version':1,'ok':ok,'status':'CROSS_PLATFORM_CAMPAIGN_READY_FOR_HUMAN_START_REVIEW' if ok else 'BLOCKED',
            'problems':sorted(set(problems)),'android_evidence_read_only':True,'windows_physical_verified':False,
            'windows_gate_count':len(gates),'windows_gates_skipped':0,'automatic_installation':False,
            'automatic_publication':False,'production_verified':False}
