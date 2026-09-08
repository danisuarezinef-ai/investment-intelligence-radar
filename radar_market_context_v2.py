"""Market Context v2 diagnostics. Scores are evidence inputs, never trade commands."""
import math

def clamp(x,a=0,b=1):return max(a,min(b,float(x)))

def expectation_surprise(actual,consensus,dispersion):
 d=abs(float(dispersion))
 return 0 if d==0 else max(-5,min(5,(float(actual)-float(consensus))/d))

def narrative_saturation(mention_percentile,positioning_percentile,valuation_percentile,novelty):
 crowd=(clamp(mention_percentile)+clamp(positioning_percentile)+clamp(valuation_percentile))/3
 return clamp(crowd*(1-.35*clamp(novelty)))

def causal_bottlenecks(graph,demand):
 """graph[node]={capacity_growth,demand_growth,criticality}; higher gap*criticality ranks bottlenecks."""
 out=[]
 for node,x in graph.items():
  gap=max(0,float(x.get('demand_growth',demand))-float(x.get('capacity_growth',0)))
  out.append({'node':node,'bottleneck_score':gap*clamp(x.get('criticality',1))})
 return sorted(out,key=lambda x:x['bottleneck_score'],reverse=True)

def cross_asset_confirmation(signals):
 """signals normalized -1..1 by equities/rates/fx/commodities/volatility/credit."""
 vals=[max(-1,min(1,float(v))) for v in signals.values()]
 if not vals:return {'direction':0,'agreement':0,'conflict':True}
 direction=sum(vals)/len(vals);agreement=1-(sum((v-direction)**2 for v in vals)/len(vals))**.5/1.0
 return {'direction':direction,'agreement':clamp(agreement),'conflict':agreement<.45}

def regime_transition(current_probs,previous_probs):
 keys=set(current_probs)|set(previous_probs);moves={k:float(current_probs.get(k,0))-float(previous_probs.get(k,0)) for k in keys}
 target=max(moves,key=moves.get) if moves else None
 magnitude=moves.get(target,0) if target else 0
 entropy=-sum(p*math.log(max(p,1e-12)) for p in map(float,current_probs.values())) if current_probs else 0
 return {'toward':target,'probability_change':magnitude,'transition_strength':clamp(magnitude*2),'entropy':entropy}
