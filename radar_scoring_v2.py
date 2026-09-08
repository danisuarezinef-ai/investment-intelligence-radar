import math
from radar_core import opportunity_rankings
from radar_learning import detect_regime

HORIZON_WEIGHTS={
 'short':{'m7':0.48,'m30':0.28,'m90':0.08,'vol':-0.16},
 'medium':{'m7':0.18,'m30':0.38,'m90':0.28,'vol':-0.16},
 'long':{'m7':0.06,'m30':0.24,'m90':0.50,'vol':-0.20},
}

def _regime_adjust(symbol,regime):
 growth={'MSFT','NVDA','GOOGL','AMZN','META','AVGO','ASML','TSM'}
 defensive={'BRK-B','V','NVS','LLY','SHEL'}
 if regime=='risk_on_growth':return 1.5 if symbol in growth else 0.2
 if regime=='risk_off':return 1.2 if symbol in defensive else -0.8 if symbol in growth else 0
 if regime=='defensive_rotation':return 1.0 if symbol in defensive else -0.4
 return 0.0

def multihorizon_rankings(limit=16):
 regime=detect_regime(False)['regime'];base=opportunity_rankings(30);items=[]
 for tier in base.values():items.extend(tier)
 uniq={x['symbol']:x for x in items};out={}
 for h,w in HORIZON_WEIGHTS.items():
  rows=[]
  for s,x in uniq.items():
   z=w['m7']*x['momentum7']+w['m30']*x['momentum30']+w['m90']*x['momentum90']+w['vol']*x['volatility']+_regime_adjust(s,regime)
   conf=max(.05,min(.95,.5+.35*math.tanh(abs(z)/12)+(0.05 if x['risk']=='bajo' else 0)))
   rows.append({'symbol':s,'horizon':h,'score':z,'confidence':conf,'risk':x['risk'],'volatility':x['volatility'],'regime':regime,'features':{'momentum7':x['momentum7'],'momentum30':x['momentum30'],'momentum90':x['momentum90'],'volatility':x['volatility']}})
  out[h]=sorted(rows,key=lambda r:r['score'],reverse=True)[:limit]
 return out

def lists_369_v2():
 r=multihorizon_rankings(30);allrows={}
 for h,rows in r.items():
  for x in rows:
   d=allrows.setdefault(x['symbol'],{'symbol':x['symbol'],'scores':{},'conf':[],'risks':[]})
   d['scores'][h]=x['score'];d['conf'].append(x['confidence']);d['risks'].append(x['risk'])
 merged=[]
 for s,d in allrows.items():
  vals=list(d['scores'].values());mean=sum(vals)/len(vals);conf=sum(d['conf'])/len(d['conf']);risk='alto' if 'alto' in d['risks'] else ('intermedio' if 'intermedio' in d['risks'] else 'bajo')
  merged.append({'symbol':s,'score':mean,'confidence':conf,'risk':risk,'scores':d['scores']})
 reliable=sorted(merged,key=lambda x:(x['confidence'],x['score']),reverse=True)[:3]
 adjusted=sorted(merged,key=lambda x:x['score']/({'bajo':1,'intermedio':1.5,'alto':2.2}[x['risk']]),reverse=True)[:6]
 promising=sorted(merged,key=lambda x:x['score'],reverse=True)[:9]
 return {'high_reliability':reliable,'best_risk_adjusted':adjusted,'promising':promising,'by_horizon':r}
