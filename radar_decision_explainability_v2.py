"""Decision explainability contract for SHADOW/PAPER decisions."""
from __future__ import annotations
REAL_TRADING=False


def explain_decision(decision):
    d=dict(decision or {})
    evidence=d.get('evidence') or []
    reasons=[]
    for item in evidence:
        if isinstance(item,dict):
            source=item.get('source') or item.get('provider') or 'UNKNOWN'
            signal=item.get('signal') or item.get('reason') or item.get('relation') or 'UNSPECIFIED'
            confidence=item.get('confidence')
            reasons.append({'source':source,'signal':signal,'confidence':confidence})
    status='EXPLAINED' if reasons and d.get('model_version') else 'INCOMPLETE_EXPLANATION'
    return {
      'status':status,
      'symbol':d.get('symbol'),
      'action':d.get('action'),
      'model_version':d.get('model_version'),
      'expected_return':d.get('expected_return'),
      'risk_score':d.get('risk_score'),
      'evidence_count':len(reasons),
      'reasons':reasons[:12],
      'provenance_required':True,
      'real_trading':False,
    }
