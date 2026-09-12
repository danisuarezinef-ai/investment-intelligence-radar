"""Evidence-derived task matrix for pre-1.6 tasks 311-370.

A task can be implemented yet remain pending.  Brain readiness is independent from the
technical gate and never enables trading/release/promotion.
"""
from __future__ import annotations

from radar_brain_calibration_v2 import confidence_decomposition, uncertainty_decomposition, abstention_decision_v3

REAL_TRADING=False
STATES={'PASS','PENDING_SAMPLE','PENDING_TIME','NOT_VERIFIED','FAILED'}


def _task(i,state,detail,*,critical=False,evidence=None):
    if state not in STATES:raise ValueError(state)
    x={'task':int(i),'state':state,'detail':str(detail),'critical':bool(critical)}
    if evidence is not None:x['evidence']=evidence
    return x


def _state(value,false='NOT_VERIFIED'):
    return 'PASS' if value is True else false


def _economic_edge_state(complete,value):
    """PASS requires an observed positive economic edge, not merely metric availability."""
    if not complete:return 'PENDING_SAMPLE'
    if not isinstance(value,(int,float)):return 'PENDING_SAMPLE'
    return 'PASS' if float(value)>0 else 'FAILED'


def build_tasks_311_370(*,technical,evidence,analytics,competition,rows=None,persistence=None,external=None):
    technical=technical or {};evidence=evidence or {};analytics=analytics or {};competition=competition or {}
    rows=list(rows or []);persistence=persistence or {};external=external or {}
    tasks={}

    # 311-325 technical closure. External observations are never self-invented.
    tasks[311]=_task(311,'PASS' if external.get('exact_sha_verified') is True else 'NOT_VERIFIED','external GitHub main SHA equals deployed Railway SHA',critical=True)
    op=technical.get('operational_health') or {}
    tasks[312]=_task(312,'PASS' if op.get('investment_score_included') is False and op.get('affects_investment_ranking') is False and op.get('affects_model_promotion') is False else 'FAILED','operational health is isolated from investment score/ranking/promotion',critical=True)
    workers=technical.get('worker_utilization') or {}
    tasks[313]=_task(313,'PASS' if workers.get('not_instrumented_is_not_zero') is True else 'NOT_VERIFIED','worker observability exposes gaps instead of treating unknown utilization as zero')
    queue=technical.get('queue') or {};probe=queue.get('controlled_probe') or {}
    tasks[314]=_task(314,'PASS' if queue.get('controlled_dlq_verified') is True and queue.get('controlled_reprocess_verified') is True and probe.get('status')=='PASS' else 'NOT_VERIFIED','controlled non-investment retry→DLQ→requeue→ACK',critical=True)
    provider=technical.get('provider') or {};cp=provider.get('controlled_probe') or {}
    tasks[315]=_task(315,'PASS' if cp.get('circuit_open_verified') is True and cp.get('half_open_verified') is True and cp.get('recovery_verified') is True else 'NOT_VERIFIED','controlled CLOSED→OPEN→HALF_OPEN→CLOSED circuit transition',critical=True)
    tasks[316]=_task(316,'PASS' if cp.get('rate_limit_backoff_verified') is True and cp.get('rate_recovery_gradual_verified') is True else 'NOT_VERIFIED','controlled 429 backoff and gradual recovery',critical=True)
    part=technical.get('partition') or {}
    tasks[317]=_task(317,'PASS' if part.get('backpressure_backend')=='SUPABASE_RETRY_QUEUE' and part.get('ack_after_remote_success') is True else 'NOT_VERIFIED','generic sync durable backpressure is wired',critical=True)
    enq=int(part.get('backpressure_enqueued') or 0);drained=int(part.get('backpressure_drained') or 0);backlog=part.get('backlog_last')
    tasks[318]=_task(318,'PASS' if enq>0 and drained>=enq and backlog==0 else 'PENDING_SAMPLE','automatic backlog drain after observed remote recovery',evidence={'enqueued':enq,'drained':drained,'backlog':backlog})
    deep151=technical.get('deep_151_200') or {};deep201=technical.get('deep_201_270') or {}
    tasks[319]=_task(319,_state(deep151.get('deep_ready')),'151-200 deep snapshot is ready',critical=True)
    tasks[320]=_task(320,_state(deep201.get('deep_ready')),'201-270 deep snapshot is ready',critical=True)
    proof=technical.get('proof') or {}
    tasks[321]=_task(321,'PASS' if proof.get('verified') is True else 'NOT_VERIFIED','deep Production Proof v3 is recorded and verified; emitted candidate alone is insufficient',critical=True)
    digest=technical.get('protected_digest') or {}
    tasks[322]=_task(322,'PASS' if digest.get('digest') and not digest.get('missing') else 'FAILED','complete protected SHA-256 digest',critical=True,evidence={'files':digest.get('files'),'missing':digest.get('missing')})
    tasks[323]=_task(323,'PASS' if external.get('tamper_test') is True else 'NOT_VERIFIED','external protected-file tamper invalidation test',critical=True)
    tasks[324]=_task(324,'PASS' if external.get('stale_deployment_test') is True else 'NOT_VERIFIED','external stale-deployment rejection test',critical=True)
    tech_required=(311,312,314,315,316,317,319,320,321,322,323,324)
    tech_ready=all(tasks[i]['state']=='PASS' for i in tech_required)
    tasks[325]=_task(325,'PASS','technical pre-1.6 gate is reproducible and separate from scientific/brain readiness',critical=True,evidence={'verdict':'READY_FOR_MANUAL_TECH_REVIEW' if tech_ready else 'BLOCKED_TECHNICAL'})

    # 326-340 canonical forward evidence.
    env=evidence.get('decision_envelope') or {}
    tasks[326]=_task(326,'PASS' if env.get('natural_envelope') is True else 'PENDING_SAMPLE','first natural transactional PAPER decision envelope',critical=True,evidence={'count':env.get('count')})
    tasks[327]=_task(327,'PASS' if env.get('provenance_complete') is True else 'PENDING_SAMPLE','transactional envelope PIT/provider/benchmark/cost provenance complete',critical=True)
    tasks[328]=_task(328,'PASS' if env.get('entry_linked_without_reconstruction') is True else 'PENDING_SAMPLE','entry linked to immutable original decision without reconstruction',critical=True)
    tasks[329]=_task(329,'PASS' if env.get('prospective_close') is True else 'PENDING_TIME','natural prospective close for exact transactional envelope',critical=True)
    tasks[330]=_task(330,'PASS' if env.get('task_150_eligible') is True else 'PENDING_SAMPLE','Task 150 closes only from verified natural envelope + prospective close',critical=True)
    dedup=evidence.get('deduplication') or {}
    tasks[331]=_task(331,'PASS' if evidence.get('canonical_key')=='prediction_hash' and int(evidence.get('rows_total') or 0)>0 else 'PENDING_SAMPLE','single canonical forward evidence authority from immutable prediction ledger',critical=True)
    tasks[332]=_task(332,'FAILED' if dedup.get('collisions') else ('PASS' if int(dedup.get('unique_n') or 0)>0 else 'PENDING_SAMPLE'),'prediction-hash deduplication prevents double counting',critical=True,evidence={'input_n':dedup.get('input_n'),'unique_n':dedup.get('unique_n'),'duplicates':len(dedup.get('duplicates') or []),'collisions':len(dedup.get('collisions') or [])})
    ess=evidence.get('ess') or {}
    tasks[333]=_task(333,'PASS' if int(ess.get('clusters') or 0)>0 else 'PENDING_SAMPLE','temporal/model/regime cluster independence audit',evidence={'clusters':ess.get('clusters'),'largest_cluster':ess.get('largest_cluster')})
    tasks[334]=_task(334,'PASS' if float(ess.get('conservative_ess') or 0)>=20 else 'PENDING_SAMPLE','ESS v2 penalizes clustered/correlated evidence',critical=True,evidence=ess)
    q=evidence.get('mean_evidence_quality');nmat=int(evidence.get('rows_matured_natural') or 0)
    tasks[335]=_task(335,'PASS' if q is not None and q>=.90 and nmat>=30 else 'PENDING_SAMPLE','Evidence Quality Score covers provenance/timing/benchmark/cost/immutability',evidence={'mean_quality':q,'matured_natural':nmat})
    horizons=evidence.get('horizons') or {};hs=[(horizons.get(h) or {}).get('status') for h in ('1d','1w','1m','3m')]
    if hs and all(x=='PASS' for x in hs):s336='PASS'
    elif any(x=='PENDING_TIME' for x in hs):s336='PENDING_TIME'
    else:s336='PENDING_SAMPLE'
    tasks[336]=_task(336,s336,'independent 1d/1w/1m/3m maturity',critical=True,evidence=horizons)
    tasks[337]=_task(337,(evidence.get('regimes') or {}).get('status','PENDING_SAMPLE'),'independent regime maturity',critical=True,evidence=evidence.get('regimes'))
    tasks[338]=_task(338,(evidence.get('sectors') or {}).get('status','PENDING_SAMPLE'),'independent sector maturity',evidence=evidence.get('sectors'))
    tasks[339]=_task(339,(evidence.get('assets') or {}).get('status','PENDING_SAMPLE'),'asset-level independence/generalization',evidence=evidence.get('assets'))
    tasks[340]=_task(340,(evidence.get('markets') or {}).get('status','PENDING_SAMPLE'),'cross-market transfer requires observed multi-market evidence',evidence=evidence.get('markets'))

    # 341-360 calibration, uncertainty, abstention and alpha.
    cal=analytics.get('calibration') or {}
    tasks[341]=_task(341,cal.get('status','PENDING_SAMPLE'),'forward-only Calibration Engine v2',critical=True,evidence={'n':cal.get('n'),'ece':cal.get('ece')})
    remote_count=persistence.get('last_remote_count')
    tasks[342]=_task(342,'PASS' if persistence.get('configured') is True and isinstance(remote_count,int) and remote_count>0 else 'NOT_VERIFIED','content-addressed reliability snapshots persist in Supabase',evidence={'configured':persistence.get('configured'),'remote_count':remote_count,'backend':persistence.get('durable_backend')})
    tasks[343]=_task(343,'PASS' if int(cal.get('n') or 0)>=30 and cal.get('brier') is not None else 'PENDING_SAMPLE','forward Brier score',evidence={'n':cal.get('n'),'brier':cal.get('brier')})
    tasks[344]=_task(344,'PASS' if int(cal.get('n') or 0)>=30 and cal.get('log_loss') is not None else 'PENDING_SAMPLE','forward log-loss',evidence={'n':cal.get('n'),'log_loss':cal.get('log_loss')})
    drift=analytics.get('drift') or {};tasks[345]=_task(345,drift.get('status','PENDING_SAMPLE') if drift.get('status') in STATES else 'NOT_VERIFIED','calibration drift detector',evidence=drift)
    sample_row=next((r for r in rows if r.get('matured') is not True),rows[-1] if rows else None)
    if sample_row:
        cd=confidence_decomposition(sample_row);ud=uncertainty_decomposition(sample_row);ad=abstention_decision_v3(sample_row)
        tasks[346]=_task(346,'PASS','confidence decomposed into reported/model/data/source/regime/lookahead/consensus components',evidence=cd)
        tasks[347]=_task(347,'PASS' if cd.get('confidence_ceiling') is not None and cd.get('adjusted_confidence')<=cd.get('confidence_ceiling') else 'FAILED','confidence ceiling prevents unsupported confidence inflation',critical=True,evidence={'ceiling':cd.get('confidence_ceiling'),'adjusted':cd.get('adjusted_confidence')})
        tasks[348]=_task(348,'PASS' if ud.get('epistemic_proxy') is not None else 'NOT_VERIFIED','epistemic and aleatoric diagnostic proxies are separated and explicitly non-identifiable',evidence=ud)
        tasks[349]=_task(349,'PASS' if ad.get('decision') in {'NO_INVERTIR / ESPERAR','EVALUABLE_PAPER_SIGNAL'} and ad.get('paper_only') is True else 'FAILED','Abstention Engine v3 is first-class and PAPER-only',critical=True,evidence=ad)
    else:
        for i,d in ((346,'confidence decomposition'),(347,'confidence ceiling'),(348,'uncertainty decomposition'),(349,'abstention engine')):tasks[i]=_task(i,'PENDING_SAMPLE',d,critical=i in (347,349))
    abst=analytics.get('abstention_quality') or {};tasks[350]=_task(350,abst.get('status','PENDING_SAMPLE'),'prospective abstention quality',critical=True,evidence=abst)
    ranking=analytics.get('ranking_369') or {};tasks[351]=_task(351,'PASS' if ranking.get('status')=='AVAILABLE' else 'PENDING_SAMPLE','uncertainty/downside/evidence-aware 3-6-9 ranking v2',evidence={'status':ranking.get('status'),'n9':len(ranking.get('top9') or [])})
    alpha=analytics.get('alpha') or {};interval=alpha.get('interval_excess') or {};down=alpha.get('downside_excess') or {}
    tasks[352]=_task(352,'PASS' if interval.get('low') is not None and interval.get('high') is not None else 'PENDING_SAMPLE','expected-return interval',evidence=interval)
    tasks[353]=_task(353,'PASS' if int(down.get('n') or 0)>0 and down.get('loss_probability') is not None else 'PENDING_SAMPLE','downside distribution',evidence=down)
    tasks[354]=_task(354,'PASS' if int(down.get('n') or 0)>=20 and down.get('expected_shortfall_05') is not None else 'PENDING_SAMPLE','tail-risk / expected-shortfall v2',evidence=down)
    cost_complete=alpha.get('status')=='PASS' and alpha.get('cost_complete') is True
    benchmark_complete=alpha.get('status')=='PASS' and alpha.get('benchmark_complete') is True
    tasks[355]=_task(355,_economic_edge_state(cost_complete,alpha.get('mean_net_return')),'cost-adjusted forward alpha must remain positive after PAPER costs',critical=True,evidence={'n':alpha.get('n'),'mean_net_return':alpha.get('mean_net_return'),'mean_cost':alpha.get('mean_cost'),'cost_complete':alpha.get('cost_complete')})
    tasks[356]=_task(356,_economic_edge_state(benchmark_complete,alpha.get('mean_excess_return')),'benchmark-relative forward alpha must be positive',critical=True,evidence={'n':alpha.get('n'),'mean_excess_return':alpha.get('mean_excess_return'),'benchmark_complete':alpha.get('benchmark_complete')})
    decay=analytics.get('decay') or {};tasks[357]=_task(357,decay.get('status','PENDING_SAMPLE'),'empirical signal half-life requires >=2 mature horizons per family',evidence=decay)
    tasks[358]=_task(358,decay.get('status','PENDING_SAMPLE'),'prediction decay by model/signal family',evidence=decay)
    attrib=analytics.get('alpha_attribution') or {}
    tasks[359]=_task(359,'PASS' if attrib.get('causal_attribution_verified') is True else 'PENDING_SAMPLE','alpha attribution cannot be promoted from observational group means to causal attribution',evidence={'status':attrib.get('status'),'causal_verified':attrib.get('causal_attribution_verified')})
    failures=analytics.get('failure_attribution') or {};tasks[360]=_task(360,failures.get('status','PENDING_SAMPLE'),'diagnostic failure attribution taxonomy',evidence={'n_failures':failures.get('n_failures'),'categories':failures.get('categories')})

    # 361-370 competition and learning readiness.
    cc=competition.get('champion_challenger') or {};tasks[361]=_task(361,'PASS' if cc.get('status')=='READY_FOR_MANUAL_COMPARISON' else 'PENDING_SAMPLE','Champion-Challenger v3 requires comparable matured forward cells',critical=True,evidence={'models':len(cc.get('models') or []),'shared_cells':cc.get('shared_cells')})
    eligible=[m for m in cc.get('models') or [] if m.get('eligible')]
    tasks[362]=_task(362,'PASS' if len(eligible)>=2 else 'PENDING_TIME','minimum Challenger incubation by natural sample + elapsed forward days',evidence={'eligible_models':len(eligible),'min_n':cc.get('min_forward_n'),'min_days':cc.get('min_forward_days')})
    deg=competition.get('champion_degradation') or {};tasks[363]=_task(363,deg.get('status','PENDING_SAMPLE') if cc.get('champion') else 'PENDING_SAMPLE','Champion degradation detector v2',evidence=deg)
    ensemble=competition.get('shadow_ensemble') or {};tasks[364]=_task(364,ensemble.get('status','PENDING_SAMPLE'),'Shadow Ensemble v2 requires >=2 eligible non-redundant forward models',evidence={'selected_models':ensemble.get('selected_models')})
    corr=ensemble.get('correlations') or {};pairs=corr.get('pairs') or {};verified_pairs=[v for v in pairs.values() if int(v.get('n') or 0)>=20 and v.get('correlation') is not None]
    tasks[365]=_task(365,'PASS' if verified_pairs else 'PENDING_SAMPLE','correlation-aware ensemble guard',evidence={'verified_pairs':len(verified_pairs),'total_pairs':len(pairs)})
    div=competition.get('diversity_reward') or {};tasks[366]=_task(366,div.get('status','PENDING_SAMPLE'),'diversity reward requires prospective incremental ensemble value',evidence=div)
    routing=competition.get('dynamic_routing') or {};model_count=len({r.get('model_version') for r in rows if r.get('model_version')})
    tasks[367]=_task(367,'PASS' if model_count>=2 and routing.get('status')=='PASS' and not routing.get('lookahead_violations') else 'PENDING_SAMPLE','dynamic routing v2 uses only outcomes known before each decision cutoff',critical=True,evidence={'models':model_count,'routing':routing})
    meta=competition.get('meta_learning') or {};tasks[368]=_task(368,meta.get('status','PENDING_SAMPLE'),'meta-learning must improve forward outcomes, not historical fit',evidence=meta)
    transfer=competition.get('historical_live_transfer') or {};tasks[369]=_task(369,transfer.get('status','PENDING_SAMPLE'),'Historical→Live Transfer Score v2',critical=True,evidence=transfer)

    brain_required=(330,332,334,336,337,341,347,349,350,355,356,361,367,369)
    brain_ready=all(tasks[i]['state']=='PASS' for i in brain_required)
    tasks[370]=_task(370,'PASS','Brain Readiness Gate is reproducible and independent of infrastructure/release authority',critical=True,evidence={'verdict':'READY' if brain_ready else 'NOT_READY','required_tasks':list(brain_required)})

    out={str(i):tasks[i] for i in range(311,371)}
    return {'status':'PRE160_TASKS_311_370','tasks':out,
            'technical_gate':{'status':'READY_FOR_MANUAL_TECH_REVIEW' if tech_ready else 'BLOCKED_TECHNICAL','manual_review_only':True},
            'brain_readiness_gate':{'status':'READY' if brain_ready else 'NOT_READY','manual_review_only':True,
                                    'automatic_promotion':False,'live_execution_allowed':False},
            'stable_windows_version':'1.5.28','setup_allowed':False,'setup_built':False,
            'automatic_release':False,'automatic_promotion':False,'automatic_demotion':False,
            'can_trade':False,'real_trading':False}
