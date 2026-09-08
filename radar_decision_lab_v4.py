"""Decision Lab v4 — longitudinal, PIT-oriented investment research primitives.
No function executes real trades. Missing evidence stays missing; assumption-based outputs are labelled.
"""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import hashlib,json,math,statistics
REAL_TRADING=False

def utcnow():return datetime.now(timezone.utc).isoformat()
def clamp(x,a=0.,b=1.):return max(a,min(b,float(x)))
def fingerprint(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

THESIS_STATES=('NEW','ACTIVE','STRENGTHENED','WEAKENED','INVALIDATED','CLOSED')
def thesis_transition(current,event):
 allowed={'NEW':{'activate':'ACTIVE','close':'CLOSED'},'ACTIVE':{'strengthen':'STRENGTHENED','weaken':'WEAKENED','kill':'INVALIDATED','close':'CLOSED'},'STRENGTHENED':{'weaken':'WEAKENED','kill':'INVALIDATED','close':'CLOSED'},'WEAKENED':{'strengthen':'STRENGTHENED','kill':'INVALIDATED','close':'CLOSED'},'INVALIDATED':{'close':'CLOSED'},'CLOSED':{}}
 if event not in allowed.get(current,{}):raise ValueError('invalid thesis transition')
 return allowed[current][event]

def freeze_forward_prediction(payload):
 p=dict(payload);p.setdefault('created_at',utcnow());p['real_trading']=False;p['immutable']=True;p['fingerprint']=fingerprint(p);return p

def mature(calendar,target_date):return target_date in set(calendar)

def reliability(records,bins=10):
 out=[]
 for i in range(bins):
  lo=i/bins;hi=(i+1)/bins;g=[r for r in records if lo<=float(r['confidence'])<(hi if i<bins-1 else hi+1e-12)]
  if g:out.append({'lo':lo,'hi':hi,'n':len(g),'forecast':sum(float(r['confidence']) for r in g)/len(g),'observed':sum(bool(r['success']) for r in g)/len(g)})
 return out

def selective_curve(records,thresholds=(0,.25,.5,.65,.75,.85)):
 out=[]
 for t in thresholds:
  g=[r for r in records if float(r.get('confidence',0))>=t]
  out.append({'threshold':t,'coverage':len(g)/len(records) if records else 0,'mean_outcome':sum(float(r.get('outcome',0)) for r in g)/len(g) if g else None})
 return out

def portfolio_attribution(rows):
 keys=('selection','sizing','sector_factor','fx','costs','cash');return {k:sum(float(r.get(k,0)) for r in rows) for k in keys}

def expected_shortfall(returns,alpha=.05):
 if not returns:return None
 x=sorted(map(float,returns));n=max(1,math.ceil(len(x)*alpha));return sum(x[:n])/n

def shrink_cov(cov,diagonal,lam=.25):
 lam=clamp(lam);return {(a,b):(1-lam)*float(v)+lam*(float(diagonal.get(a,0)) if a==b else 0.) for (a,b),v in cov.items()}

def scenario_result(weights,exposures,shocks,empirical=False,provenance=None):
 impacts={s:sum(float(exposures.get(s,{}).get(f,0))*float(v) for f,v in shocks.items()) for s in weights}
 return {'impact':sum(float(weights[s])*impacts[s] for s in weights),'asset_impacts':impacts,'empirical':bool(empirical),'assumption_based':not empirical,'provenance':provenance}

def price_decomposition(total_return,**parts):return {'total_return':float(total_return),'components':{k:float(v) for k,v in parts.items()},'unexplained':float(total_return)-sum(map(float,parts.values()))}

def evidence_conflict(items):
 by={}
 for x in items:by.setdefault(x.get('claim'),[]).append(x)
 return [{'claim':k,'sources':v,'penalty':min(.8,.15*(len({str(x.get('value')) for x in v})-1))} for k,v in by.items() if len({str(x.get('value')) for x in v})>1]

def stale_decay(age,half_life):
 if half_life is None or half_life<=0:return None
 return .5**(float(age)/float(half_life))

def cluster_duplicates(items):
 groups={}
 for x in items:groups.setdefault(x.get('story_fingerprint') or fingerprint(x.get('canonical_text','')),[]).append(x)
 return list(groups.values())

def evidence_strength(novelty,corroboration,quality):return clamp(quality)*(0.35*clamp(novelty)+0.65*clamp(corroboration))

@dataclass(frozen=True)
class Expectation:
 subject:str; expected:float; dispersion:float; known_at:str; source:str

def event_study(event_index,returns,pre=5,post=5):
 lo=max(0,event_index-pre);hi=min(len(returns),event_index+post+1);window=list(map(float,returns[lo:hi]));return {'window':window,'cumulative':sum(window),'truncated':lo!=event_index-pre or hi!=event_index+post+1}

@dataclass(frozen=True)
class CausalEdge:
 source:str; target:str; confidence:float; first_known_at:str; provenance:str; falsification:list

def bottleneck_score(capacity_growth,demand_growth,criticality):return max(0,float(demand_growth)-float(capacity_growth))*clamp(criticality)

def cross_asset(signals):
 vals=list(map(float,signals.values()));mean=sum(vals)/len(vals) if vals else 0;spread=statistics.pstdev(vals) if len(vals)>1 else 0
 return {'direction':mean,'agreement':clamp(1-spread),'conflict':spread>.55}

def transition_probability(previous,current):
 keys=set(previous)|set(current);moves={k:float(current.get(k,0))-float(previous.get(k,0)) for k in keys};target=max(moves,key=moves.get) if moves else None;return {'toward':target,'delta':moves.get(target,0) if target else 0}

def research_record(question,evidence,conclusion,decision_impact):return {'question':question,'evidence':evidence,'conclusion':conclusion,'decision_impact':decision_impact,'created_at':utcnow(),'later_correctness':None}
def realized_voi(before_utility,after_utility,research_cost=0):return float(after_utility)-float(before_utility)-float(research_cost)

def committee_record(votes):
 scores=[float(v.get('score',0)) for v in votes];return {'votes':votes,'consensus':sum(scores)/len(scores) if scores else 0,'disagreement':statistics.pstdev(scores) if len(scores)>1 else 0}
def red_team_gate(conviction,attacks):return {'required':float(conviction)>=.75,'max_attack':max([float(a.get('severity',0))*float(a.get('plausibility',0)) for a in attacks] or [0]),'attacks':attacks}
def premortem_record(failure_modes):return {'created_at':utcnow(),'failure_modes':failure_modes,'evaluated':False}

def decision_quality(data_quality,calibration,process_completeness,thesis_precommit,independence):return sum(map(clamp,[data_quality,calibration,process_completeness,thesis_precommit,independence]))/5
def regret(chosen,best_ex_post):return {'regret':float(best_ex_post)-float(chosen),'hindsight_only':True}
def opportunity_breadth(scores):return {'n':len(scores),'positive':sum(float(x)>0 for x in scores),'dispersion':statistics.pstdev(map(float,scores)) if len(scores)>1 else 0}

def liquidity_tier(adv_usd):
 x=float(adv_usd);return 'A' if x>=100_000_000 else 'B' if x>=20_000_000 else 'C' if x>=5_000_000 else 'D'
def capacity_limit(adv_usd,max_participation=.01):return max(0,float(adv_usd))*clamp(max_participation)
def tax_simulation(gains,tax_rate,jurisdiction=None):return {'after_tax':float(gains)*(1-clamp(tax_rate)),'jurisdiction':jurisdiction,'optional_simulation':True}
def fx_risk(weights,asset_fx,base_currency):return {'base_currency':base_currency,'gross_foreign_weight':sum(float(w) for a,w in weights.items() if asset_fx.get(a,base_currency)!=base_currency)}

def pit_membership(asset,at,rows):return any(r['asset']==asset and r['valid_from']<=at and (r.get('valid_to') is None or at<r['valid_to']) and r['known_at']<=at for r in rows)
def survivorship_audit(has_pit_membership,has_delistings,has_actions):return {'pass':all((has_pit_membership,has_delistings,has_actions)),'survivorship_bias_risk':not all((has_pit_membership,has_delistings,has_actions))}
def quarantine(value,peer_values,z=8):
 p=list(map(float,peer_values));sd=statistics.pstdev(p) if len(p)>1 else 0;mu=sum(p)/len(p) if p else 0;flag=bool(sd and abs(float(value)-mu)/sd>z);return {'quarantined':flag,'zscore':abs(float(value)-mu)/sd if sd else 0}
def drift(reference,current,threshold=.20):
 keys=set(reference)|set(current);delta=sum(abs(float(current.get(k,0))-float(reference.get(k,0))) for k in keys)/max(1,len(keys));return {'drift':delta,'alert':delta>threshold}

def dashboard_trace(prediction,thesis,debate,decision,allocation,outcome=None,attribution=None):return {'prediction':prediction,'thesis':thesis,'debate':debate,'decision':decision,'allocation':allocation,'outcome':outcome,'attribution':attribution,'real_trading':False}
def audit_bundle(recommendation,evidence,model_version,commit):
 p={'recommendation':recommendation,'evidence':evidence,'model_version':model_version,'commit':commit,'created_at':utcnow(),'real_trading':False};p['bundle_hash']=fingerprint(p);return p

def promotion_ready(tests_green,brain_compatible,ledger_integrity,real_trading=False):return bool(tests_green and brain_compatible and ledger_integrity and not real_trading)
def baseline_challenge(complex_score,simple_score,min_gain=.0):return {'gain':float(complex_score)-float(simple_score),'keep_complexity':float(complex_score)-float(simple_score)>float(min_gain)}
def ablation_value(full,ablated):return float(full)-float(ablated)
def complexity_gate(values,min_durable_gain=.0):return {'retain':sum(map(float,values))/len(values)>min_durable_gain if values else False,'n':len(values)}
def autonomous_sandbox(proposal):return {'proposal':proposal,'can_research':True,'can_experiment':True,'can_promote':False,'can_trade':False}
def reproducibility(seed,cutoff,data_snapshot_ids,commit,parameters):return {'seed':seed,'cutoff':cutoff,'data_snapshot_ids':data_snapshot_ids,'commit':commit,'parameters':parameters}
def negative_result(hypothesis,reason,evidence):return {'hypothesis':hypothesis,'reason':reason,'evidence':evidence,'retain':True,'created_at':utcnow()}
def thesis_conflicts(theses):
 out=[]
 for i,a in enumerate(theses):
  for b in theses[i+1:]:
   shared=set(a.get('assumptions',[]))&set(b.get('assumptions',[]))
   if shared:out.append({'a':a.get('symbol'),'b':b.get('symbol'),'shared_assumptions':sorted(shared)})
 return out
def evidence_concentration(recommendations):
 counts={};total=0
 for r in recommendations:
  for e in set(r.get('evidence_keys',[])):counts[e]=counts.get(e,0)+1;total+=1
 return {'max_share':max(counts.values())/max(1,len(recommendations)) if counts else 0,'counts':counts}
def final_release_audit(ci,tests,survivorship_ok,sync_ok,real_trading):return {'pass':all((ci,tests,survivorship_ok,sync_ok,not real_trading)),'real_trading':False}
