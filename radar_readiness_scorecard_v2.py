"""Production readiness scorecard v2 with separate PAPER/SHADOW and REAL gates."""
from __future__ import annotations
REAL_TRADING=False


def readiness_scorecard(*,windows_ok=False,cloud_ok=False,persistence_ok=False,market_ok=False,forward_integrity_ok=False,mature_forward_n=0,promotion_gate_ready=False,real_broker_connected=False):
    paper_checks={
      'windows':bool(windows_ok),'cloud':bool(cloud_ok),'persistence':bool(persistence_ok),'market':bool(market_ok),
      'forward_integrity':bool(forward_integrity_ok),'promotion_gate':bool(promotion_gate_ready),
    }
    paper_pass=sum(paper_checks.values());paper_total=len(paper_checks);paper_pct=round(100*paper_pass/paper_total,1)
    paper_state='READY_PAPER' if all(paper_checks.values()) else 'BLOCKED_PAPER'
    real_checks={**paper_checks,'mature_forward_evidence':int(mature_forward_n)>=100,'real_broker_connected':bool(real_broker_connected),'real_trading_flag':REAL_TRADING is True}
    real_state='READY_REAL' if all(real_checks.values()) else 'BLOCKED_REAL'
    return {'paper_shadow':{'status':paper_state,'score_pct':paper_pct,'checks':paper_checks},'real_money':{'status':real_state,'checks':real_checks},'mature_forward_n':int(mature_forward_n),'real_trading':False}
