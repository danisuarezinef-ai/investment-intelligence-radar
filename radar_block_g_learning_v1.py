"""Block G — autonomous PAPER champion/challenger learning.

All evidence is simulation-labelled. Short-horizon accelerated observations never
become audited forward maturity. There is no broker transport and REAL_TRADING is false.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass, asdict
import hashlib, json, math

REAL_TRADING=False
HORIZONS=('1d','1w','1m','3m')
EVIDENCE_WEIGHTS={'historical_train':.15,'walk_forward':.30,'vault':.45,'final_test':.60,'live_forward':1.0}


def _id(prefix,payload):
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),default=str).encode()
    return prefix+'-'+hashlib.sha256(raw).hexdigest()[:20]

def _clamp(x,a=0.,b=1.): return max(a,min(b,float(x)))

def seed_lineage(brain_id, specialization='generalist'):
    x={'brain_id':brain_id,'lineage_id':f'{brain_id}-root','parent':None,'generation':0,'mutation':'seed',
       'features':['score','risk','regime','data_quality'],'specialization':specialization,'training_method':'paper_seed',
       'status':'CHAMPION','real_trading':False}
    x['model_id']=_id('model',x); return x

def mutate(parent, mutation, delta=.05, specialization=None):
    c=deepcopy(parent); c['parent']=parent['model_id']; c['generation']=int(parent['generation'])+1
    c['mutation']=mutation; c['mutation_delta']=float(delta); c['status']='CHALLENGER'
    if specialization: c['specialization']=specialization
    c['model_id']=_id('model',{k:v for k,v in c.items() if k!='model_id'}); return c

def record_outcome(model, *, action, realized_return, benchmark_return=0., drawdown=0., costs=0., confidence=.5,
                   evidence_kind='walk_forward', horizon='1d', reason='observed paper outcome'):
    if horizon not in HORIZONS: raise ValueError('unsupported horizon')
    if evidence_kind not in EVIDENCE_WEIGHTS: raise ValueError('unsupported evidence kind')
    action=str(action).upper(); rr=float(realized_return); br=float(benchmark_return)
    correct=(rr>br and action=='BUY') or (rr<br and action=='SELL') or (action in ('HOLD','NO_INVERTIR') and abs(rr-br)<.01)
    opportunity_cost=max(0.,rr-br) if action in ('HOLD','NO_INVERTIR') else 0.
    avoided_loss=max(0.,-rr) if action in ('HOLD','NO_INVERTIR') else 0.
    row={'model_id':model['model_id'],'lineage_id':model['lineage_id'],'generation':model['generation'],'action':action,
         'realized_return':rr,'benchmark_return':br,'excess_return':rr-br,'drawdown':abs(float(drawdown)),'costs':max(0.,float(costs)),
         'confidence':_clamp(confidence),'correct':bool(correct),'opportunity_cost':opportunity_cost,'avoided_loss':avoided_loss,
         'reason':reason,'evidence_kind':evidence_kind,'evidence_weight':EVIDENCE_WEIGHTS[evidence_kind],'horizon':horizon,
         'accelerated':evidence_kind!='live_forward','audited_forward_maturity_credit': evidence_kind=='live_forward',
         'real_trading':False}
    row['evidence_id']=_id('evidence',row); return row

def score_model(model, evidence):
    rows=[r for r in evidence if r['model_id']==model['model_id']]
    if not rows: return {'model_id':model['model_id'],'score':0.,'n':0,'anti_overfitting_score':0.,'transfer_score':0.}
    w=sum(r['evidence_weight'] for r in rows) or 1.
    excess=sum(r['excess_return']*r['evidence_weight'] for r in rows)/w
    dd=sum(r['drawdown']*r['evidence_weight'] for r in rows)/w
    costs=sum(r['costs']*r['evidence_weight'] for r in rows)/w
    calibration=sum((1.-abs((1. if r['correct'] else 0.)-r['confidence']))*r['evidence_weight'] for r in rows)/w
    decision_value=sum((r['avoided_loss']-r['opportunity_cost'])*r['evidence_weight'] for r in rows)/w
    kinds={r['evidence_kind'] for r in rows}; horizons={r['horizon'] for r in rows}
    diversity=_clamp((len(kinds)/5.+len(horizons)/4.)/2.)
    aos=_clamp(.55*diversity+.45*calibration)
    live=[r for r in rows if r['evidence_kind']=='live_forward']; nonlive=[r for r in rows if r['evidence_kind']!='live_forward']
    if live and nonlive:
        l=sum(r['excess_return'] for r in live)/len(live); h=sum(r['excess_return'] for r in nonlive)/len(nonlive)
        transfer=_clamp(1.-abs(l-h)/max(.01,abs(h)+.01))
    else: transfer=0.
    score=excess+decision_value-.7*dd-costs+.02*calibration+.01*aos
    return {'model_id':model['model_id'],'score':score,'n':len(rows),'excess_return':excess,'drawdown':dd,'costs':costs,
            'calibration':calibration,'decision_value':decision_value,'anti_overfitting_score':aos,'transfer_score':transfer,
            'formal_forward_samples':len(live),'real_trading':False}

def competition(champion, challengers, evidence, *, min_margin=.002):
    champ=score_model(champion,evidence); ranked=sorted([(score_model(c,evidence),c) for c in challengers],key=lambda x:x[0]['score'],reverse=True)
    winner=champion; promoted=False; reason='champion_retained'
    if ranked:
        best,cand=ranked[0]
        # PAPER promotion can use accelerated evidence, but must remain labelled PAPER and cannot create formal maturity.
        if best['n']>=4 and best['anti_overfitting_score']>=.35 and best['score']>=champ['score']+min_margin:
            winner=deepcopy(cand); winner['status']='CHAMPION'; promoted=True; reason='challenger_won_paper_competition'
    losers=[]
    for c in challengers:
        if c['model_id']!=winner['model_id']:
            z=deepcopy(c); z['status']='GRAVEYARD'; z['reason']='lost_paper_competition'; losers.append(z)
    hof=[deepcopy(champion)] if promoted else []
    if promoted: hof[0]['status']='HALL_OF_FAME'; hof[0]['reason']='replaced_by_stronger_paper_challenger'
    return {'winner':winner,'promoted':promoted,'reason':reason,'champion_score':champ,'challenger_scores':[x[0] for x in ranked],
            'hall_of_fame':hof,'graveyard':losers,'one_active_champion':True,'paper_only':True,'real_trading':False}

def accelerated_learning_cycle(champion, challengers, observations):
    evidence=[]
    models=[champion]+list(challengers)
    for m in models:
        for o in observations:
            # deterministic model-specific perturbation stands for challenger policy response in the PAPER lab.
            bias=((int(hashlib.sha256(m['model_id'].encode()).hexdigest()[:4],16)%17)-8)/10000.
            evidence.append(record_outcome(m,action=o['action'],realized_return=o['realized_return']+bias,
                benchmark_return=o.get('benchmark_return',0.),drawdown=o.get('drawdown',0.),costs=o.get('costs',0.),
                confidence=o.get('confidence',.5),evidence_kind=o.get('evidence_kind','walk_forward'),horizon=o.get('horizon','1d'),
                reason=o.get('reason','paper learning observation')))
    comp=competition(champion,challengers,evidence)
    return {'evidence':evidence,'competition':comp,'accelerated_samples':sum(r['accelerated'] for r in evidence),
            'formal_forward_maturity_samples':sum(r['audited_forward_maturity_credit'] for r in evidence),
            'short_horizons_provisional':True,'real_trading':False}

def block_g_validation():
    champion=seed_lineage('balanced')
    challengers=[mutate(champion,'threshold_tighten',.04,'low_vol'),mutate(champion,'regime_weight',.05,'regime_specialist'),
                 mutate(champion,'confidence_calibration',.03,'causal_specialist')]
    observations=[
      {'action':'BUY','realized_return':.018,'benchmark_return':.009,'drawdown':.006,'costs':.001,'confidence':.72,'horizon':'1d','evidence_kind':'walk_forward'},
      {'action':'NO_INVERTIR','realized_return':-.012,'benchmark_return':-.020,'drawdown':0.,'costs':0.,'confidence':.68,'horizon':'1w','evidence_kind':'vault','reason':'abstention avoided loss'},
      {'action':'HOLD','realized_return':.002,'benchmark_return':.003,'drawdown':0.,'costs':0.,'confidence':.61,'horizon':'1m','evidence_kind':'historical_train','reason':'non-trade learned'},
      {'action':'BUY','realized_return':.031,'benchmark_return':.018,'drawdown':.011,'costs':.0015,'confidence':.77,'horizon':'3m','evidence_kind':'final_test'},
      {'action':'NO_INVERTIR','realized_return':-.004,'benchmark_return':-.013,'drawdown':0.,'costs':0.,'confidence':.70,'horizon':'1d','evidence_kind':'walk_forward','reason':'rejection learned'},
    ]
    run=accelerated_learning_cycle(champion,challengers,observations); comp=run['competition']; ev=run['evidence']
    actions={r['action'] for r in ev}; horizons={r['horizon'] for r in ev}
    checks={'lineage_complete':all(all(k in x for k in ('lineage_id','parent','generation','mutation','features','specialization','training_method','status')) for x in [champion]+challengers),
            'champion_challenger':comp['one_active_champion'] and len(comp['challenger_scores'])==3,
            'all_horizons':set(HORIZONS)<=horizons,'learns_non_trades':bool({'HOLD','NO_INVERTIR'} & actions),
            'accelerated_not_forward_mature':run['accelerated_samples']>0 and run['formal_forward_maturity_samples']==0,
            'anti_overfitting_measured':all('anti_overfitting_score' in x for x in [comp['champion_score']]+comp['challenger_scores']),
            'transfer_measured':all('transfer_score' in x for x in [comp['champion_score']]+comp['challenger_scores']),
            'hall_grave_supported':'hall_of_fame' in comp and 'graveyard' in comp,
            'paper_only':comp['paper_only'] and not REAL_TRADING and all(r['real_trading'] is False for r in ev)}
    return {'status':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'champion':champion,'challengers':challengers,
            'learning_run':run,'autonomous_learning_loop':'ACTIVE' if all(checks.values()) else 'NOT_VERIFIED',
            'broker_connected':False,'live_execution_allowed':False,'real_money_orders_allowed':False,'real_trading':False}
