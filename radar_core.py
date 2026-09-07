import os, sqlite3, json, urllib.request, urllib.parse, csv, io, math, statistics
from datetime import datetime, timezone, timedelta

APP='Investment Intelligence Radar'
DATA=os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'InvestmentIntelligenceRadarData')
os.makedirs(DATA, exist_ok=True)
DB=os.path.join(DATA,'radar.db'); STATUS=os.path.join(DATA,'status.json'); PID=os.path.join(DATA,'worker.pid'); LOG=os.path.join(DATA,'worker.log')
UA='InvestmentIntelligenceRadar/1.2.1 contact=danisuarezinef@gmail.com'
ASSETS={'MSFT':'msft.us','NVDA':'nvda.us','GOOGL':'googl.us','AMZN':'amzn.us','META':'meta.us','AVGO':'avgo.us','ASML':'asml.us','SAP':'sap.us','TSM':'tsm.us','TM':'tm.us','SHEL':'shel.us','RIO':'rio.us','LLY':'lly.us','V':'v.us','BRK-B':'brk-b.us','NVS':'nvs.us'}

def now(): return datetime.now(timezone.utc).isoformat()
def con():
    c=sqlite3.connect(DB,timeout=20); c.execute('PRAGMA journal_mode=WAL'); return c

def _cols(c,t):
    try:return {r[1] for r in c.execute('pragma table_info('+t+')')}
    except:return set()
def _ensure(c,n,req,ddl):
    cols=_cols(c,n)
    if cols and not set(req).issubset(cols):
        base=n+'_legacy'; legacy=base; i=1; names={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        while legacy in names:i+=1; legacy=base+'_'+str(i)
        c.execute('alter table '+n+' rename to '+legacy)
    c.execute(ddl)

def init_db():
    c=con()
    _ensure(c,'market_snapshots',{'id','ts','symbol','price','volume','source'},'create table if not exists market_snapshots(id integer primary key,ts text,symbol text,price real,volume real,source text)')
    _ensure(c,'information_events',{'id','ts','source','title','url','category'},'create table if not exists information_events(id integer primary key,ts text,source text,title text,url text unique,category text)')
    _ensure(c,'system_runs',{'id','ts','job','status','detail'},'create table if not exists system_runs(id integer primary key,ts text,job text,status text,detail text)')
    _ensure(c,'control',{'key','value'},'create table if not exists control(key text primary key,value text)')
    c.execute('create table if not exists paper_account(id integer primary key check(id=1),cash real not null,initial_cash real not null,enabled integer not null default 0,last_rebalance text)')
    c.execute('create table if not exists paper_positions(symbol text primary key,qty real not null,avg_price real not null,updated_at text not null)')
    c.execute('create table if not exists paper_trades(id integer primary key,ts text,symbol text,side text,qty real,price real,value real,reason text)')
    c.execute('create table if not exists portfolio_values(id integer primary key,ts text,total real,cash real,invested real)')
    c.execute('create index if not exists idx_market_symbol_ts on market_snapshots(symbol,ts)')
    c.commit(); c.close()

def write_status(**kw):
    cur={}
    try:
        if os.path.exists(STATUS):cur=json.load(open(STATUS,'r',encoding='utf-8'))
    except:pass
    cur.update(kw); cur['heartbeat']=now(); tmp=STATUS+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:json.dump(cur,f,ensure_ascii=False,indent=2)
    os.replace(tmp,STATUS)
def log(job,status,detail=''):
    init_db(); c=con(); c.execute('insert into system_runs(ts,job,status,detail) values(?,?,?,?)',(now(),job,status,detail[:4000])); c.commit(); c.close(); write_status(last_job=job,last_status=status,last_detail=detail)

def fetch(url,timeout=18,headers=None):
    h={'User-Agent':UA,'Accept':'application/json,text/plain,*/*','Connection':'close'}
    if headers:h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read().decode('utf-8','replace')

def _history_stooq(code,days=390,host='stooq.com'):
    end=datetime.now(timezone.utc).date(); start=end-timedelta(days=days)
    u=f'https://{host}/q/d/l/?s={urllib.parse.quote(code)}&d1={start:%Y%m%d}&d2={end:%Y%m%d}&i=d'
    txt=fetch(u,20)
    rows=[]
    for r in csv.DictReader(io.StringIO(txt)):
        try:
            d=r.get('Date'); close=float(r.get('Close')); vol=r.get('Volume')
            if not d:continue
            ts=d+'T21:00:00+00:00'; rows.append((ts,close,float(vol) if vol not in (None,'','N/D','-') else None))
        except:continue
    if len(rows)<2:raise RuntimeError(host+' sin histórico válido')
    return rows

def _quote_yahoo(sym,host='query1.finance.yahoo.com'):
    ys=urllib.parse.quote(sym,safe=''); u=f'https://{host}/v8/finance/chart/{ys}?interval=1d&range=5d'
    data=json.loads(fetch(u,15)); result=(data.get('chart') or {}).get('result') or []
    if not result:raise RuntimeError(host+' sin resultado')
    meta=result[0].get('meta') or {}; q=((result[0].get('indicators') or {}).get('quote') or [{}])[0]
    price=meta.get('regularMarketPrice')
    if price is None:price=next((x for x in reversed(q.get('close') or []) if x is not None),None)
    if price is None:raise RuntimeError(host+' sin precio')
    vol=next((x for x in reversed(q.get('volume') or []) if x is not None),None)
    return float(price),(float(vol) if vol is not None else None),'Yahoo Finance'

def history_ready():
    init_db(); c=con(); n=c.execute("select count(distinct substr(ts,1,10)) from market_snapshots where source='Stooq Historical'").fetchone()[0]; c.close(); return n>=20

def collect_history(days=390):
    init_db(); added=0; failures=[]; c=con()
    for sym,code in ASSETS.items():
        hist=None
        for host in ('stooq.com','stooq.pl'):
            try:hist=_history_stooq(code,days,host); break
            except Exception as e:failures.append(sym+' '+host+': '+str(e))
        if not hist:continue
        for ts,price,vol in hist:
            if not c.execute('select 1 from market_snapshots where symbol=? and ts=? limit 1',(sym,ts)).fetchone():
                c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(ts,sym,price,vol,'Stooq Historical')); added+=1
    c.commit(); c.close(); status='OK' if added or history_ready() else 'ERROR'; log('history',status,f'{added} puntos históricos añadidos'+((' · '+failures[0]) if failures and not added else '')); write_status(history_status=status,history_added=added,last_history_errors=failures[:4]); return added

def collect_market():
    init_db(); ok=0; errs=[]; sources={}
    for sym,code in ASSETS.items():
        value=None; failures=[]
        for host in ('query1.finance.yahoo.com','query2.finance.yahoo.com'):
            try:value=_quote_yahoo(sym,host); break
            except Exception as e:failures.append(host+': '+str(e))
        if value is None:
            for host in ('stooq.com','stooq.pl'):
                try:
                    h=_history_stooq(code,10,host); ts,price,vol=h[-1]; value=(price,vol,'Stooq Daily'); break
                except Exception as e:failures.append(host+': '+str(e))
        if value is None:errs.append(sym+': '+' | '.join(failures)[:500]); continue
        price,volume,source=value; c=con(); c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(now(),sym,price,volume,source)); c.commit(); c.close(); ok+=1; sources[source]=sources.get(source,0)+1
    status='OK' if ok else 'ERROR'; detail=f'{ok}/{len(ASSETS)} precios guardados'
    if sources:detail+=' · '+', '.join(f'{k} {v}' for k,v in sources.items())
    if errs:detail+=' · errores: '+'; '.join(errs[:2])
    log('market',status,detail); write_status(market_status=status,market_source=', '.join(sources) or 'sin fuente',prices_added=ok,last_market_errors=errs[:6]); return ok

def collect_science():
    init_db(); q=urllib.parse.quote('artificial intelligence OR semiconductor OR battery OR fusion energy OR quantum computing'); u='https://www.ebi.ac.uk/europepmc/webservices/rest/search?query='+q+'&format=json&pageSize=15'; n=0
    try:
        data=json.loads(fetch(u)); results=data.get('resultList',{}).get('result',[]); c=con()
        for r in results:
            title=(r.get('title') or '').strip(); pid=r.get('pmid') or r.get('pmcid') or r.get('id')
            if not title or not pid:continue
            url='https://europepmc.org/article/MED/'+str(pid)
            try:c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'Europe PMC',title,url,'science')); n+=1
            except sqlite3.IntegrityError:pass
        c.commit(); c.close(); log('science','OK',f'{n} eventos nuevos de {len(results)} recuperados'); write_status(science_status='OK',science_seen=len(results))
    except Exception as e:log('science','ERROR',str(e)); write_status(science_status='ERROR',last_error=str(e))
    return n

def collect_sec():
    init_db(); tickers={'MSFT':'0000789019','NVDA':'0001045810','AMZN':'0001018724','META':'0001326801','GOOGL':'0001652044'}; n=0; failures=[]; c=con()
    for sym,cik in tickers.items():
        try:
            data=json.loads(fetch(f'https://data.sec.gov/submissions/CIK{cik}.json',15,{'Accept-Encoding':'identity'})); recent=data.get('filings',{}).get('recent',{}); forms=recent.get('form',[]); acc=recent.get('accessionNumber',[]); docs=recent.get('primaryDocument',[])
            for i,form in enumerate(forms[:40]):
                if form not in ('8-K','10-Q','10-K','6-K','20-F'):continue
                a=acc[i].replace('-',''); doc=docs[i]; url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{doc}'; title=f'{sym} · SEC {form}'
                try:c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'SEC EDGAR',title,url,'regulatory')); n+=1
                except sqlite3.IntegrityError:pass
        except Exception as e:failures.append(sym+': '+str(e))
    c.commit(); c.close(); status='OK' if n or len(failures)<len(tickers) else 'ERROR'; log('sec',status,f'{n} eventos SEC nuevos'+((' · '+'; '.join(failures[:2])) if failures else '')); write_status(sec_status=status,last_sec_errors=failures[:4]); return n

def stats():
    init_db(); c=con(); p=c.execute('select count(*) from market_snapshots').fetchone()[0]; e=c.execute('select count(*) from information_events').fetchone()[0]; r=c.execute('select count(*) from system_runs').fetchone()[0]; latest=c.execute("select symbol,price,source,ts from market_snapshots where source!='Stooq Historical' order by id desc limit 16").fetchall(); news=c.execute('select source,title,ts from information_events order by id desc limit 12').fetchall(); c.close(); return p,e,r,latest,news

def _daily_series(symbol,days=365):
    c=con(); since=(datetime.now(timezone.utc)-timedelta(days=days+8)).isoformat(); rows=c.execute('select ts,price from market_snapshots where symbol=? and ts>=? order by ts',(symbol,since)).fetchall(); c.close(); byday={}
    for ts,p in rows:
        try:byday[str(ts)[:10]]=float(p)
        except:pass
    return sorted(byday.items())
def _ret(rows):return ((rows[-1][1]/rows[0][1])-1)*100 if len(rows)>=2 and rows[0][1] else None
def _vol(rows):
    if len(rows)<4:return 0.0
    rs=[]
    for i in range(1,len(rows)):
        a,b=rows[i-1][1],rows[i][1]
        if a>0 and b>0:rs.append(math.log(b/a))
    return statistics.pstdev(rs)*math.sqrt(252)*100 if len(rs)>2 else 0.0

def profitability_leaders(days,limit=5):
    out=[]
    for s in ASSETS:
        rows=_daily_series(s,days); val=_ret(rows)
        if val is not None:out.append({'symbol':s,'return_pct':val,'points':len(rows)})
    return sorted(out,key=lambda x:x['return_pct'],reverse=True)[:limit]

def opportunity_rankings(limit=5):
    rows=[]
    for s in ASSETS:
        d7=_daily_series(s,7); d30=_daily_series(s,30); d90=_daily_series(s,90); m7=_ret(d7); m30=_ret(d30); m90=_ret(d90); vol=_vol(d90)
        if m30 is None:continue
        m7=0 if m7 is None else m7; m90=m30 if m90 is None else m90; score=0.35*m7+0.40*m30+0.25*m90-0.20*vol; risk='bajo' if vol<22 else ('intermedio' if vol<38 else 'alto')
        rows.append({'symbol':s,'score':score,'risk':risk,'momentum7':m7,'momentum30':m30,'momentum90':m90,'volatility':vol})
    result={k:[] for k in ('bajo','intermedio','alto')}
    for r in sorted(rows,key=lambda x:x['score'],reverse=True):
        if len(result[r['risk']])<limit:result[r['risk']].append(r)
    return result

def paper_start(amount=1000.0):
    init_db(); amount=max(100.0,float(amount))
    if not history_ready():collect_history()
    c=con(); c.execute('delete from paper_positions'); c.execute('delete from paper_trades'); c.execute('delete from portfolio_values'); c.execute('insert or replace into paper_account(id,cash,initial_cash,enabled,last_rebalance) values(1,?,?,1,null)',(amount,amount)); c.commit(); c.close(); paper_step(force=True); return paper_status()
def paper_toggle():
    init_db(); c=con(); row=c.execute('select enabled from paper_account where id=1').fetchone()
    if not row:c.close(); return paper_start(1000.0)
    v=0 if row[0] else 1; c.execute('update paper_account set enabled=? where id=1',(v,)); c.commit(); c.close(); return paper_status()
def _latest_prices():
    c=con(); d={}
    for s in ASSETS:
        row=c.execute('select price from market_snapshots where symbol=? order by ts desc,id desc limit 1',(s,)).fetchone()
        if row:d[s]=float(row[0])
    c.close(); return d
def paper_status():
    init_db(); prices=_latest_prices(); c=con(); a=c.execute('select cash,initial_cash,enabled,last_rebalance from paper_account where id=1').fetchone()
    if not a:c.close(); return {'configured':False,'cash':0,'initial':0,'enabled':False,'total':0,'pnl':0,'pnl_pct':0,'positions':[],'trades':[]}
    pos=c.execute('select symbol,qty,avg_price from paper_positions order by symbol').fetchall(); trades=c.execute('select ts,symbol,side,qty,price,value,reason from paper_trades order by id desc limit 12').fetchall(); cash=float(a[0]); invested=0; plist=[]
    for s,q,avg in pos:
        p=prices.get(s,float(avg)); value=q*p; invested+=value; plist.append({'symbol':s,'qty':q,'avg_price':avg,'price':p,'value':value,'pnl_pct':((p/avg)-1)*100 if avg else 0})
    total=cash+invested; initial=float(a[1]); c.close(); return {'configured':True,'cash':cash,'initial':initial,'enabled':bool(a[2]),'last_rebalance':a[3],'total':total,'invested':invested,'pnl':total-initial,'pnl_pct':((total/initial)-1)*100 if initial else 0,'positions':plist,'trades':[{'ts':x[0],'symbol':x[1],'side':x[2],'qty':x[3],'price':x[4],'value':x[5],'reason':x[6]} for x in trades]}
def paper_step(force=False):
    st=paper_status()
    if not st.get('configured') or not st.get('enabled'):return st
    if not history_ready():collect_history(); st=paper_status()
    if not force and st.get('last_rebalance'):
        try:
            if (datetime.now(timezone.utc)-datetime.fromisoformat(st['last_rebalance'])).total_seconds()<1800:return st
        except:pass
    ranks=opportunity_rankings(8); candidates=ranks['bajo'][:3]+ranks['intermedio'][:2]; prices=_latest_prices()
    if not candidates or len(prices)<3:return st
    c=con(); scoremap={r['symbol']:r['score'] for tier in ranks.values() for r in tier}
    for p in st['positions']:
        if p['symbol'] not in scoremap or scoremap[p['symbol']]<0 or p['pnl_pct']<-6.0:
            price=prices.get(p['symbol'])
            if not price:continue
            value=p['qty']*price; c.execute('update paper_account set cash=cash+? where id=1',(value,)); c.execute('delete from paper_positions where symbol=?',(p['symbol'],)); c.execute('insert into paper_trades(ts,symbol,side,qty,price,value,reason) values(?,?,?,?,?,?,?)',(now(),p['symbol'],'SELL',p['qty'],price,value,'Salida por deterioro/riesgo'))
    c.commit(); c.close(); st=paper_status(); total=st['total']; target_invested=total*0.70; per_cap=total*0.18; need=max(0,target_invested-st.get('invested',0)); c=con(); cash=st['cash']; held={p['symbol']:p for p in st['positions']}
    for r in candidates:
        if need<25 or cash<25:break
        s=r['symbol']; price=prices.get(s)
        if not price or price<=0 or s in held or r['score']<=0:continue
        spend=min(per_cap,need,cash*0.95)
        if spend<25:continue
        qty=spend/price; c.execute('update paper_account set cash=cash-? where id=1',(spend,)); c.execute('insert or replace into paper_positions(symbol,qty,avg_price,updated_at) values(?,?,?,?)',(s,qty,price,now())); c.execute('insert into paper_trades(ts,symbol,side,qty,price,value,reason) values(?,?,?,?,?,?,?)',(now(),s,'BUY',qty,price,spend,f"Score {r['score']:.2f} · riesgo {r['risk']}")); cash-=spend; need-=spend
    c.execute('update paper_account set last_rebalance=? where id=1',(now(),)); c.commit(); c.close(); st=paper_status(); c=con(); c.execute('insert into portfolio_values(ts,total,cash,invested) values(?,?,?,?)',(now(),st['total'],st['cash'],st.get('invested',0))); c.commit(); c.close(); return st
