"""Investment-first UI view model. Presentation only; no execution side effects."""
from __future__ import annotations
from typing import Any
REAL_TRADING=False

def investment_home(*, account:dict[str,Any], decision:dict[str,Any]|None, opportunities:list[dict[str,Any]],
                    scorecard:dict[str,Any], cloud:dict[str,Any], promotion:dict[str,Any])->dict[str,Any]:
    return {'capital':{'equity':account.get('equity'),'cash':account.get('cash'),'invested':account.get('invested')},
            'recommendation':decision or {'action':'WAIT','reason':'INSUFFICIENT_EVIDENCE'},
            'top_opportunities':opportunities[:10],'forward_evidence':scorecard,'cloud_health':cloud,
            'promotion':promotion,'performance_label':'FORWARD' if scorecard.get('performance_verified') else 'INSUFFICIENT_EVIDENCE',
            'execution_mode':'PAPER_OR_SHADOW_ONLY','can_trade':False,'real_trading':False}
