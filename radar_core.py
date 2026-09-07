import os, sqlite3, json, urllib.request, urllib.parse, csv, io
from datetime import datetime, timezone

APP='Investment Intelligence Radar'
DATA=os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'InvestmentIntelligenceRadarData')
os.makedirs(DATA, exist_ok=True)
DB=os.path.join(DATA,'radar.db')
STATUS=os.path.join(DATA,'status.json')
PID=os.path.join(DATA,'worker.pid')
LOG=os.path.join(DATA,'worker.log')
UA='InvestmentIntelligenceRadar/1.1 contact=danisuarezinef@gmail.com'

ASSETS={
 'MSFT':'msft.us','NVDA':'nvda.us','GOOGL':'googl.us','AMZN':'amzn.us','META':'meta.us','AVGO':'avgo.us',
 'ASML':'asml.us','SAP':'sap.us','TSM':'tsm.us','TM':'tm.us','SHEL':'shel.us','RIO':'rio.us','LLY':'lly.us','V':'v.us','BRK-B':'brk-b.us','NVS':'nvs.us'
}
YAHOO={k:('BRK-B' if k=='BRK-B' else k) for k in ASSETS}

def now(): return datetime.now(timezone.utc).isoformat()

def con():
    c=sqlite3.connect(DB, timeout=15)
    c.execute('PRAGMA journal_mode=WAL')
    return c

def init_db():
    c=con()
    c.executescript('''
    create table if not exists market_snapshots(id integer primary key, ts text, symbol text, price real, volume real, source text);
    create table if not exists information_events(id integer primary key, ts text, source text, title text, url text unique, category text);
    create table if not exists system_runs(id integer primary key, ts text, job text, status text, detail text);
    create table if not exists control(key text primary key, value text);
    ''')
    c.commit(); c.close()

def write_status(**kw):
    cur={}
    try:
        if os.path.exists(STATUS): cur=json.load(open(STATUS,'r',encoding='utf-8'))
    except Exception: pass
    cur.update(kw); cur['heartbeat']=now()
    tmp=STATUS+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f: json.dump(cur,f,ensure_ascii=False,indent=2)
    os.replace(tmp,STATUS)

def log(job,status,detail=''):
    c=con(); c.execute('insert into system_runs(ts,job,status,detail) values(?,?,?,?)',(now(),job,status,detail[:4000])); c.commit(); c.close()
    write_status(last_job=job,last_status=status,last_detail=detail)

def fetch(url, timeout=15, headers=None):
    h={'User-Agent':UA,'Accept':'application/json,text/plain,*/*'}
    if headers: h.update(headers)
    req=urllib.request.Request(url,headers=h)
    with urllib.request.urlopen(req,timeout=timeout) as r: return r.read().decode('utf-8','replace')

def _market_stooq(sym,stooq):
    txt=fetch('https://stooq.com/q/l/?s='+urllib.parse.quote(stooq)+'&f=sd2t2ohlcv&h&e=csv',10)
    rows=list(csv.DictReader(io.StringIO(txt)))
    if not rows: raise RuntimeError('Stooq sin filas')
    row=rows[0]; close=row.get('Close')
    if not close or close in ('N/D','-'): raise RuntimeError('Stooq sin precio')
    vol=row.get('Volume')
    return float(close), (float(vol) if vol and vol not in ('N/D','-') else None), 'Stooq'

def _market_yahoo(sym):
    ys=urllib.parse.quote(YAHOO.get(sym,sym),safe='')
    data=json.loads(fetch(f'https://query1.finance.yahoo.com/v8/finance/chart/{ys}?interval=1d&range=5d',10))
    result=(data.get('chart') or {}).get('result') or []
    if not result: raise RuntimeError('Yahoo sin resultado')
    meta=result[0].get('meta') or {}
    price=meta.get('regularMarketPrice')
    if price is None:
        closes=(((result[0].get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
        price=next((x for x in reversed(closes) if x is not None),None)
    if price is None: raise RuntimeError('Yahoo sin precio')
    vol=None
    volumes=(((result[0].get('indicators') or {}).get('quote') or [{}])[0].get('volume') or [])
    if volumes: vol=next((x for x in reversed(volumes) if x is not None),None)
    return float(price), (float(vol) if vol is not None else None), 'Yahoo Finance'

def collect_market():
    ok=0; errs=[]; sources={}
    for sym,stooq in ASSETS.items():
        value=None; failures=[]
        for getter in (lambda:_market_stooq(sym,stooq),lambda:_market_yahoo(sym)):
            try:
                value=getter(); break
            except Exception as e: failures.append(str(e))
        if value is None:
            errs.append(sym+': '+' / '.join(failures)[:220]); continue
        price,volume,source=value
        c=con(); c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(now(),sym,price,volume,source)); c.commit(); c.close(); ok+=1
        sources[source]=sources.get(source,0)+1
    status='OK' if ok else 'ERROR'
    detail=f'{ok}/{len(ASSETS)} precios guardados'
    if sources: detail+=' · '+', '.join(f'{k} {v}' for k,v in sources.items())
    if errs: detail+=' · errores: '+'; '.join(errs[:2])
    log('market',status,detail); write_status(market_status=status,market_source=', '.join(sources) or 'sin fuente',prices_added=ok,last_market_errors=errs[:4])
    return ok

def collect_science():
    q=urllib.parse.quote('artificial intelligence OR semiconductor OR battery OR fusion energy OR quantum computing')
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?query='+q+'&format=json&pageSize=15'
    n=0
    try:
        data=json.loads(fetch(url)); results=data.get('resultList',{}).get('result',[])
        c=con()
        for r in results:
            title=(r.get('title') or '').strip(); pid=r.get('pmid') or r.get('pmcid') or r.get('id')
            if not title or not pid: continue
            u='https://europepmc.org/article/MED/'+str(pid)
            try: c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'Europe PMC',title,u,'science')); n+=1
            except sqlite3.IntegrityError: pass
        c.commit(); c.close(); log('science','OK',f'{n} eventos nuevos de {len(results)} recuperados'); write_status(science_status='OK',science_seen=len(results))
    except Exception as e:
        log('science','ERROR',str(e)); write_status(science_status='ERROR',last_error=str(e))
    return n

def collect_sec():
    tickers={'MSFT':'0000789019','NVDA':'0001045810','AMZN':'0001018724','META':'0001326801','GOOGL':'0001652044'}
    n=0; failures=[]
    c=con()
    for sym,cik in tickers.items():
        try:
            data=json.loads(fetch(f'https://data.sec.gov/submissions/CIK{cik}.json',15,{'Accept-Encoding':'identity'}))
            recent=data.get('filings',{}).get('recent',{})
            forms=recent.get('form',[]); acc=recent.get('accessionNumber',[]); docs=recent.get('primaryDocument',[])
            for i,form in enumerate(forms[:40]):
                if form not in ('8-K','10-Q','10-K','6-K','20-F'): continue
                a=acc[i].replace('-',''); doc=docs[i]; url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{doc}'
                title=f'{sym} · SEC {form}'
                try: c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'SEC EDGAR',title,url,'regulatory')); n+=1
                except sqlite3.IntegrityError: pass
        except Exception as e: failures.append(sym+': '+str(e))
    c.commit(); c.close()
    status='OK' if n or len(failures)<len(tickers) else 'ERROR'
    detail=f'{n} eventos SEC nuevos' + ((' · '+'; '.join(failures[:2])) if failures else '')
    log('sec',status,detail); write_status(sec_status=status,last_sec_errors=failures[:4])
    return n

def stats():
    init_db(); c=con()
    prices=c.execute('select count(*) from market_snapshots').fetchone()[0]
    events=c.execute('select count(*) from information_events').fetchone()[0]
    runs=c.execute('select count(*) from system_runs').fetchone()[0]
    latest=c.execute('select symbol,price,source,ts from market_snapshots order by id desc limit 16').fetchall()
    news=c.execute('select source,title,ts from information_events order by id desc limit 12').fetchall()
    c.close(); return prices,events,runs,latest,news
