"""Gate-approved PAPER execution authority. Never sends real orders."""
from radar_paper_portfolio_v5 import record_fill
REAL_TRADING=False

def execute_paper_allocations(governance, allocations, prices, fee_rate=0.001):
    if not governance or governance.get('paper_execution_allowed') is not True:
        return {'status':'BLOCKED_BY_PROMOTION_GATE','executed':[],'real_trading':False}
    out=[]
    for a in allocations or []:
        if a.get('prediction_evidence')!='VERIFIED_FORWARD':continue
        symbol=a.get('symbol');amount=float(a.get('amount') or 0);px=(prices or {}).get(symbol)
        if not symbol or amount<=0 or not isinstance(px,(int,float)) or px<=0:continue
        qty=amount/float(px);fee=amount*max(0.0,float(fee_rate))
        out.append(record_fill(symbol=symbol,side='BUY',quantity=qty,price=float(px),cost=fee,decision={'source':'PAPER_AUTHORITY_V2','allocation':a},backfilled=False))
    return {'status':'PAPER_EXECUTED' if out else 'NO_ELIGIBLE_ALLOCATIONS','executed':out,'automatic_scope':'PAPER_ONLY','can_trade':False,'real_trading':False}
