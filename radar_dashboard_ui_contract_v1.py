"""Presentation contract for Windows operational dashboard."""
REAL_TRADING=False

def ui_contract(payload):
    p=payload or {};balance=p.get('balance') or {};forward=p.get('forward_evidence') or {};market=p.get('market') or {}
    return {'title':'Radar de Inversión','primary_cards':[{'id':'equity','label':'Saldo PAPER','value':balance.get('equity')},{'id':'cash','label':'Efectivo','value':balance.get('cash')},{'id':'drawdown','label':'Drawdown','value':balance.get('drawdown_pct')},{'id':'evidence','label':'Evidencia forward','value':p.get('evidence_state')}],'sections':{'positions':p.get('positions') or [],'learning_state':p.get('learning_state'),'optimizer_state':p.get('optimizer_state'),'market_coverage':{'observed':market.get('assets_observed'),'expected':market.get('assets_expected')},'forward':{'predictions':forward.get('predictions'),'matured':forward.get('matured')}},'banner':'REAL TRADING OFF','refreshable':True,'real_trading':False}
