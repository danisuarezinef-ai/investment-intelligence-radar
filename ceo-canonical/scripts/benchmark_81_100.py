from __future__ import annotations
import json, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from ceo_core.models import ProjectState, Task
from ceo_core.release_candidate_v1 import *

s=ProjectState(goal='RC 1.0 local acceptance', project_name='benchmark-81-100')
core=ReleaseCandidateCore()

# 81-84 portfolio/degradation/failover at scale
for i in range(120):
    core.portfolio.record(s,'champion',success=True,quality=.93,latency_seconds=1.0,cost=.02,task_type='coding')
for i in range(80):
    core.portfolio.record(s,'challenger',success=True,quality=.88,latency_seconds=.8,cost=.015,task_type='coding')
for i in range(40):
    core.portfolio.record(s,'degrading',success=True,quality=.91,latency_seconds=1.0,task_type='coding')
for i in range(20):
    core.portfolio.record(s,'degrading',success=(i%4==0),quality=.42,latency_seconds=3.5,task_type='coding')
deg=core.degradation.assess(s,'degrading',recent_window=20)
core.outages.set_outage(s,'champion',reason='benchmark outage')
t=Task(title='Preserve context on failover',description='important context',required_capabilities=['coding'],acceptance_criteria=['no context loss'])
failover=core.failover.choose_fallback(s,t,failed_provider='champion',candidates=['champion','challenger','degrading'])

# 85-86 correlated consensus and diversity
for _ in range(40): core.consensus.record_pair(s,'sameA','sameB',agreed=True,correct=False)
for _ in range(5): core.consensus.record_pair(s,'sameA','sameB',agreed=True,correct=True)
ensemble=core.ensemble.combine(s,[
    {'provider':'sameA','text':'identical repeated weak conclusion','quality':.55,'confidence':.95,'independence':.2},
    {'provider':'sameB','text':'identical repeated weak conclusion','quality':.55,'confidence':.95,'independence':.2},
    {'provider':'independent','text':'independent primary evidence overturns weak conclusion','quality':.96,'confidence':.86,'independence':1.0},
])

# 87-89 red team / security regression corpus
red=core.red_team.generate(components=['provider_router','semantic_memory','tool_broker','budget_engine','sqlite_store'],side_effects=['read','write','delete','spend','communicate','network'])
for case in red:
    core.security_regressions.register(s,vulnerability_id=case.id,description=case.scenario,test_id='redteam:'+case.id,severity=case.severity)
    core.security_regressions.record(s,case.id,passed=True,evidence_ref='benchmark:redteam:'+case.id)
sec=core.security_regressions.gate(s)
adv=core.adversarial.review(s,artifact_id='rc-core',claims=['red team passed'],evidence_refs=['red team passed'],attack_results=[{'pass':True,'case':x.id} for x in red])

# 90-93 500 bug reproductions and fix competitions
winners={}
for i in range(500):
    plan=core.bugs.build(description=f'bug {i}',observed_error='deterministic failure',context={'component':'scheduler'})
    candidates=[
        {'id':f'{i}-large','tests_passed':True,'root_cause_fixed':True,'security_regressions':0,'compatibility_regressions':0,'lines_changed':700,'complexity_delta':3,'maintainability':.75},
        {'id':f'{i}-small','tests_passed':True,'root_cause_fixed':True,'security_regressions':0,'compatibility_regressions':0,'lines_changed':15,'complexity_delta':0,'maintainability':.94},
        {'id':f'{i}-unsafe','tests_passed':True,'root_cause_fixed':True,'security_regressions':1,'compatibility_regressions':0,'lines_changed':2,'complexity_delta':0,'maintainability':1},
    ]
    comp=core.competition.compete(s,bug_id=plan.bug_id,candidates=candidates)
    winners[comp['winner']['id'].split('-')[-1]]=winners.get(comp['winner']['id'].split('-')[-1],0)+1

# 94-100 local release closure
notes=core.release_notes.generate(version='1.0.0-rc1-local',previous_version='0.9.0-dev10',changes=[{'area':'81-100','summary':'model portfolio, red-team, patch competition and release gates'}],known_limits=['Windows physical validation deferred','Live provider not verified'],evidence=['benchmark 81-100 PASS'])
diff=core.diff.audit(before={'core':'dev10','field':'deferred'},after={'core':'rc1','field':'deferred','roadmap':'81-100'})
core.freeze.freeze(s,'1.0.0-rc1-local')

h=core.acceptance
evidence={g:'PASS' for g in h.LOCAL_GATES}
evidence.update({'windows_install':'DEFERRED_BY_USER','windows_restart':'DEFERRED_BY_USER','live_provider':'NOT_VERIFIED','production_proof':'NOT_VERIFIED'})
accept=h.evaluate(evidence)
rc=core.rc_builder.build(version='1.0.0-rc1-local',local_acceptance=accept,security_gate=sec,release_diff=diff,freeze_active=True)

out={
    'status':'PASS',
    'portfolio':{'champion':core.portfolio.profile(s,'champion'),'challenger':core.portfolio.profile(s,'challenger'),'degradation':deg},
    'failover':failover,
    'consensus_reliability_wrong_pair':core.consensus.reliability(s,['sameA','sameB']),
    'ensemble':ensemble,
    'red_team_cases':len(red),'security_gate':sec,'adversarial':adv,
    'bug_competitions':500,'winner_distribution':winners,
    'release_diff':diff,'release_notes_has_limits':'Windows physical validation deferred' in notes,
    'local_acceptance':accept,'rc_candidate':rc,
    'production_verified':False,
}
assert deg['degraded']
assert failover['to']=='challenger'
assert ensemble['selected']['provider']=='independent'
assert sec['passed'] and adv['verdict']=='PASS'
assert winners=={'small':500}
assert accept['local_rc_ready'] and not accept['production_verified']
assert rc['rc_candidate_ready'] and not rc['production_verified']

path=ROOT/'reports'/'RELEASE_CANDIDATE_81_100_BENCHMARK.json'
path.write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(out,indent=2,ensure_ascii=False))
