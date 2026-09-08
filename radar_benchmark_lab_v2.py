"""Benchmark Lab v2: complexity must beat simple controls out of sample."""
import math

def max_drawdown(rs):
 wealth=peak=1.;dd=0.
 for r in rs:wealth*=1+float(r);peak=max(peak,wealth);dd=max(dd,1-wealth/peak)
 return dd

def stats(rs):
 rs=[float(x) for x in rs];n=len(rs)
 if not n:return {'n':0,'mean':0,'vol':0,'sharpe':0,'max_drawdown':0}
 mean=sum(rs)/n;vol=math.sqrt(sum((x-mean)**2 for x in rs)/max(1,n-1));return {'n':n,'mean':mean,'vol':vol,'sharpe':mean/vol if vol else 0,'max_drawdown':max_drawdown(rs)}

def benchmark_suite(strategy_returns,benchmark_returns,cash_returns=None):
 cash_returns=cash_returns or [0]*len(strategy_returns)
 return {'strategy':stats(strategy_returns),'benchmark':stats(benchmark_returns),'cash':stats(cash_returns),'excess_mean':stats(strategy_returns)['mean']-stats(benchmark_returns)['mean']}

def abstention_value(records):
 """records: outcome return and abstain bool; measures avoided loss/opportunity cost separately."""
 abst=[r for r in records if r.get('abstain')];act=[r for r in records if not r.get('abstain')]
 avoided=sum(max(0,-float(r.get('outcome',0))) for r in abst);missed=sum(max(0,float(r.get('outcome',0))) for r in abst)
 return {'n_abstain':len(abst),'n_active':len(act),'avoided_loss':avoided,'missed_upside':missed,'net_abstention_value':avoided-missed}

def calibration(records,bins=5):
 out=[]
 for i in range(bins):
  lo=i/bins;hi=(i+1)/bins;g=[r for r in records if lo<=float(r['confidence'])<=(hi if i==bins-1 else hi-1e-12)]
  if g:out.append({'lo':lo,'hi':hi,'n':len(g),'confidence':sum(float(r['confidence']) for r in g)/len(g),'success':sum(bool(r['success']) for r in g)/len(g)})
 return out

def marginal_signal_value(full,ablated):return float(full)-float(ablated)

def redundancy(correlation,threshold=.85):
 return sorted([(a,b,float(v)) for (a,b),v in correlation.items() if a<b and abs(float(v))>=threshold],key=lambda x:abs(x[2]),reverse=True)

def information_half_life(lag_scores):
 """First lag where predictive magnitude falls to <= half initial magnitude."""
 if not lag_scores:return None
 ks=sorted(lag_scores);base=abs(float(lag_scores[ks[0]]));target=base/2
 return next((k for k in ks if abs(float(lag_scores[k]))<=target),None)
