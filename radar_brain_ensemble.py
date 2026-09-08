"""Regime-aware ensemble layer. Disagreement is treated as uncertainty, not averaged away."""
from __future__ import annotations
import math


def _softmax(xs,temp=.35):
    if not xs:return []
    m=max(xs);z=[math.exp((x-m)/max(.05,temp)) for x in xs];s=sum(z);return [x/s for x in z]


def ensemble_prediction(predictions,regime='mixed'):
    """predictions: [{lineage,score,confidence,regime_score,transfer_score,status}]"""
    if not predictions:return {'score':0,'confidence':0,'uncertainty':1,'members':[],'abstain':True}
    eligible=[p for p in predictions if p.get('status') in ('active','shadow','hall_of_fame')]
    if not eligible:return {'score':0,'confidence':0,'uncertainty':1,'members':[],'abstain':True}
    quality=[]
    for p in eligible:
        transfer=max(-1,min(1,float(p.get('transfer_score',0))))
        regime_fit=float(p.get('regime_score',.5));confidence=float(p.get('confidence',.5))
        quality.append(.45*confidence+.35*regime_fit+.20*((transfer+1)/2))
    weights=_softmax(quality);scores=[float(p.get('score',0)) for p in eligible]
    mean=sum(w*s for w,s in zip(weights,scores));variance=sum(w*(s-mean)**2 for w,s in zip(weights,scores));disagreement=math.sqrt(variance)
    uncertainty=min(1.0,disagreement/25.0);base_conf=sum(w*float(p.get('confidence',.5)) for w,p in zip(weights,eligible));confidence=max(0,min(1,base_conf*(1-uncertainty)))
    members=[{'lineage':p.get('lineage'),'weight':round(w,4),'score':p.get('score')} for p,w in zip(eligible,weights)]
    return {'score':mean,'confidence':confidence,'uncertainty':uncertainty,'members':members,'abstain':confidence<.35 or uncertainty>.65,'regime':regime}


def ensemble_diversity(predictions):
    if len(predictions)<2:return 0.0
    vals=[float(p.get('score',0)) for p in predictions];m=sum(vals)/len(vals);sd=math.sqrt(sum((x-m)**2 for x in vals)/len(vals));return min(1.0,sd/30.0)
