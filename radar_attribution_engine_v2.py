"""Forward-only attribution for mature PAPER/SHADOW outcomes."""
REAL_TRADING=False

def attribute(outcome, signals=None):
    o=outcome or {};signals=signals or {}
    if o.get('backfilled') is True:return {'status':'REJECTED_BACKFILL','attributable':False,'real_trading':False}
    required=('net_return','benchmark_return','excess_return','cost')
    if any(o.get(k) is None for k in required):return {'status':'INSUFFICIENT_EVIDENCE','attributable':False,'missing':[k for k in required if o.get(k) is None],'real_trading':False}
    excess=float(o['excess_return']);den=sum(abs(float(v)) for v in signals.values() if isinstance(v,(int,float)))
    contrib={}
    if den>0:
        for k,v in signals.items():
            if isinstance(v,(int,float)):contrib[str(k)]=excess*(abs(float(v))/den)
    return {'status':'ATTRIBUTED','attributable':True,'net_return':float(o['net_return']),'benchmark_return':float(o['benchmark_return']),'excess_return':excess,'cost':float(o['cost']),'signal_contributions':contrib,'optimality_claim':'NOT VERIFIED','real_trading':False}
