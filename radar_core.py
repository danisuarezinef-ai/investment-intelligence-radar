import os, sqlite3, json, time, urllib.request, urllib.parse, csv, io
from datetime import datetime, timezone

APP='Investment Intelligence Radar'
DATA=os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'InvestmentIntelligenceRadarData')
os.makedirs(DATA, exist_ok=True)
DB=os.path.join(DATA,'radar.db')
STATUS=os.path.join(DATA,'status.json')
PID=os.path.join(DATA,'worker.pid')
LOG=os.path.join(DATA,'worker.log')
UA='InvestmentIntelligenceRadar/1.0 contact=owner@example.com'

ASSETS={
 'MSFT':'msft.us','NVDA':'nvda.us','GOOGL':'googl.us','AMZN':'amzn.us','META':'meta.us','AVGO':'avgo.us',
 'ASML':'asml.us','SAP':'sap.us','TSM':'tsm.us','TM':'tm.us','SHEL':'shel.us','RIO':'rio.us','LLY':'lly.us','V':'v.us','BRK-B':'brk-b.us','NVS':'nvs.us'
}

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

def fetch(url, timeout=15):
    req=urllib.request.Request(url, headers={'User-Agent':UA})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read().decode('utf-8','replace')

def collect_market():
    ok=0; errs=[]
    for sym,stooq in ASSETS.items():
        try:
            txt=fetch('https://stooq.com/q/l/?s='+urllib.parse.quote(stooq)+'&f=sd2t2ohlcv&h&e=csv')
            rows=list(csv.DictReader(io.StringIO(txt)))
            if not rows: continue
            row=rows[0]; close=row.get('Close')
            if not close or close in ('N/D','-'): continue
            price=float(close); vol=row.get('Volume')
            volume=float(vol) if vol and vol not in ('N/D','-') else None
            c=con(); c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(now(),sym,price,volume,'Stooq')); c.commit(); c.close(); ok+=1
        except Exception as e: errs.append(sym+': '+str(e))
    status='OK' if ok else 'ERROR'; detail=f'{ok} precios guardados' + ((' | '+'; '.join(errs[:3])) if errs else '')
    log('market',status,detail); write_status(market_status=status,market_source='Stooq',prices_added=ok)
    return ok

def collect_science():
    q=urllib.parse.quote('artificial intelligence OR semiconductor OR battery OR fusion energy OR quantum computing')
    url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?query='+q+'&format=json&pageSize=15&sort=CITED desc'
    n=0
    try:
        data=json.loads(fetch(url)); results=data.get('resultList',{}).get('result',[])
        c=con()
        for r in results:
            title=(r.get('title') or '').strip(); pid=r.get('pmid') or r.get('pmcid') or r.get('id')
            if not title or not pid: continue
            u='https://europepmc.org/article/MED/'+str(pid)
            try:
                c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'Europe PMC',title,u,'science')); n+=1
            except sqlite3.IntegrityError: pass
        c.commit(); c.close(); log('science','OK',f'{n} eventos nuevos'); write_status(science_status='OK')
    except Exception as e:
        log('science','ERROR',str(e)); write_status(science_status='ERROR',last_error=str(e))
    return n

def collect_sec():
    tickers={'MSFT':'0000789019','NVDA':'0001045810','AMZN':'0001018724','META':'0001326801','GOOGL':'0001652044'}
    n=0
    try:
        c=con()
        for sym,cik in tickers.items():
            try:
                data=json.loads(fetch(f'https://data.sec.gov/submissions/CIK{cik}.json'))
                recent=data.get('filings',{}).get('recent',{})
                forms=recent.get('form',[]); acc=recent.get('accessionNumber',[]); docs=recent.get('primaryDocument',[])
                for i,form in enumerate(forms[:40]):
                    if form not in ('8-K','10-Q','10-K','6-K','20-F'): continue
                    a=acc[i].replace('-',''); doc=docs[i]; url=f'https://www.sec.gov/Archives/edgar/data/{int(cik)}/{a}/{doc}'
                    title=f'{sym} · SEC {form}'
                    try: c.execute('insert into information_events(ts,source,title,url,category) values(?,?,?,?,?)',(now(),'SEC EDGAR',title,url,'regulatory')); n+=1
                    except sqlite3.IntegrityError: pass
            except Exception: pass
        c.commit(); c.close(); log('sec','OK',f'{n} eventos nuevos'); write_status(sec_status='OK')
    except Exception as e:
        log('sec','ERROR',str(e)); write_status(sec_status='ERROR',last_error=str(e))
    return n

def stats():
    init_db(); c=con()
    prices=c.execute('select count(*) from market_snapshots').fetchone()[0]
    events=c.execute('select count(*) from information_events').fetchone()[0]
    runs=c.execute('select count(*) from system_runs').fetchone()[0]
    latest=c.execute('select symbol,price,source,ts from market_snapshots order by id desc limit 12').fetchall()
    news=c.execute('select source,title,ts from information_events order by id desc limit 10').fetchall()
    c.close(); return prices,events,runs,latest,news
