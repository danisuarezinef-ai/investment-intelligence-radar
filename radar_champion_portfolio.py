"""Champion paper portfolio. Simulation only; REAL_TRADING is hard-disabled."""
from __future__ import annotations
import math, statistics
from radar_core import con, init_db, now, _latest_prices
from radar_risk_engine_v1 import portfolio_risk_gate

REAL_TRADING=False
INITIAL_CASH=200.0
TARGET_INVESTED=.70
MAX_POSITION=.20
MAX_POSITIONS=5
STOP_LOSS=-8.0
FEE_PCT=.0010
SPREAD_PCT=.0010
FX_PCT=.0007

def init_champion_db():
    init_db(); c=con()
    c.execute('''create table if not exists champion_paper_account(id integer primary key check(id=1),initial_cash real not null,cash real not null,enabled integer not null default 1,created_at text not null,last_step text)''')
    c.execute('''create table if not exists champion_paper_positions(symbol text primary key,qty real not null,avg_price real not null,updated_at text not null)''')
    c.execute('''create table if not exists champion_paper_trades(id integer primary key,ts text not null,symbol text not null,side text not null,qty real not null,price real not null,gross real not null,costs real not null,reason text)''')
    c.execute('''create table if not exists champion_paper_marks(id integer primary key,ts text not null,total real not null,cash real not null,invested real not null,drawdown_pct real not null default 0)''')
    if not c.execute('select 1 from champion_paper_account where id=1').fetchone():c.execute('insert into champion_paper_account(id,initial_cash,cash,enabled,created_at) values(1,?,?,1,?)',(INITIAL_CASH,INITIAL_CASH,now()))
    c.commit();c.close()

def reset_champion(initial_cash=INITIAL_CASH):
    init_champion_db();amount=max(50.0,float(initial_cash));c=con();c.execute('delete from champion_paper_positions');c.execute('delete from champion_paper_trades');c.execute('delete from champion_paper_marks');c.execute('update champion_paper_account set initial_cash=?,cash=?,enabled=1,created_at=?,last_step=null where id=1',(amount,amount,now()));c.commit();c.close();return champion_status()

def _cost(gross):return gross*(FEE_PCT+SPREAD_PCT+FX_PCT)
def _risk_metrics(vals):
    vals=[float(x) for x in vals if x and float(x)>0]
    if not vals:return {'max_drawdown_pct':0.0,'sharpe':0.0,'marks':0}
    peak=vals[0];maxdd=0.0;rets=[]
    for i,v in enumerate(vals):
        peak=max(peak,v);maxdd=min(maxdd,(v/peak-1)*100 if peak else 0.0)
        if i and vals[i-1]>0:rets.append(v/vals[i-1]-1)
    sd=statistics.pstdev(rets) if len(rets)>1 else 0.0;mean=statistics.mean(rets) if rets else 0.0
    return {'max_drawdown_pct':maxdd,'sharpe':mean/sd*math.sqrt(252) if sd>1e-12 else 0.0,'marks':len(vals)}

def champion_status():
    init_champion_db();prices=_latest_prices();c=con();a=c.execute('select initial_cash,cash,enabled,last_step from champion_paper_account where id=1').fetchone();rows=c.execute('select symbol,qty,avg_price from champion_paper_positions order by symbol').fetchall();marks=[r[0] for r in c.execute('select total from champion_paper_marks order by id').fetchall()];trades=c.execute('select ts,symbol,side,qty,price,gross,costs,reason from champion_paper_trades order by id desc limit 20').fetchall();c.close();pos=[];invested=0.0
    for sym,qty,avg in rows:
        px=float(prices.get(sym,avg));value=float(qty)*px;invested+=value;pos.append({'symbol':sym,'qty':float(qty),'avg_price':float(avg),'price':px,'value':value,'pnl_pct':(px/float(avg)-1)*100 if avg else 0.0})
    initial=float(a[0]);cash=float(a[1]);total=cash+invested
    return {'configured':True,'initial':initial,'cash':cash,'enabled':bool(a[2]),'last_step':a[3],'invested':invested,'total':total,'pnl':total-initial,'pnl_pct':(total/initial-1)*100 if initial else 0.0,'positions':pos,'trades':[{'ts':r[0],'symbol':r[1],'side':r[2],'qty':r[3],'price':r[4],'gross':r[5],'costs':r[6],'reason':r[7]} for r in trades],**_risk_metrics(marks),'real_trading':False}

def _mark():
    st=champion_status();c=con();prior=c.execute('select max(total) from champion_paper_marks').fetchone()[0];peak=max(float(prior or 0),st['total']);dd=(st['total']/peak-1)*100 if peak else 0.0;c.execute('insert into champion_paper_marks(ts,total,cash,invested,drawdown_pct) values(?,?,?,?,?)',(now(),st['total'],st['cash'],st['invested'],dd));c.commit();c.close();return champion_status()

def step_champion(decision):
    """Execute a risk-gated paper-only interpretation of the Champion decision."""
    init_champion_db();st=champion_status()
    if not st['enabled']:return st
    prices=_latest_prices();candidates=decision.get('candidates') or [];allowed={x.get('symbol') for x in candidates[:5] if x.get('symbol') and float(x.get('champion_score') or 0)>0};c=con()
    for p in st['positions']:
        px=prices.get(p['symbol'])
        if not px:continue
        weak=(p['symbol'] not in allowed and bool(candidates)) or p['pnl_pct']<=STOP_LOSS
        if not weak:continue
        gross=p['qty']*px;costs=_cost(gross);net=max(0.0,gross-costs);c.execute('update champion_paper_account set cash=cash+? where id=1',(net,));c.execute('delete from champion_paper_positions where symbol=?',(p['symbol'],));c.execute('insert into champion_paper_trades(ts,symbol,side,qty,price,gross,costs,reason) values(?,?,?,?,?,?,?,?)',(now(),p['symbol'],'SELL',p['qty'],px,gross,costs,'Champion risk/ranking exit'))
    c.commit();c.close();st=champion_status()
    if decision.get('action')!='PAPER_BUY_CANDIDATE' or not decision.get('symbol'):
        c=con();c.execute('update champion_paper_account set last_step=? where id=1',(now(),));c.commit();c.close();return _mark()
    sym=decision['symbol'];px=prices.get(sym);held={p['symbol'] for p in st['positions']}
    if not px or sym in held:
        c=con();c.execute('update champion_paper_account set last_step=? where id=1',(now(),));c.commit();c.close();return _mark()
    risk=portfolio_risk_gate(st,decision,limits={'max_position':MAX_POSITION,'max_invested':TARGET_INVESTED,'max_positions':MAX_POSITIONS})
    budget=float(risk['allowed_budget'])
    if budget>=10:
        rate=FEE_PCT+SPREAD_PCT+FX_PCT;gross=budget/(1+rate);costs=_cost(gross);qty=gross/px;c=con();c.execute('update champion_paper_account set cash=cash-?,last_step=? where id=1',(gross+costs,now()));c.execute('insert into champion_paper_positions(symbol,qty,avg_price,updated_at) values(?,?,?,?)',(sym,qty,px,now()));c.execute('insert into champion_paper_trades(ts,symbol,side,qty,price,gross,costs,reason) values(?,?,?,?,?,?,?,?)',(now(),sym,'BUY',qty,px,gross,costs,f"Champion risk-gated confidence {float(decision.get('confidence') or 0):.3f}; multiplier {risk['risk_multiplier']:.3f}"));c.commit();c.close()
    else:
        c=con();c.execute('update champion_paper_account set last_step=? where id=1',(now(),));c.commit();c.close()
    return _mark()
