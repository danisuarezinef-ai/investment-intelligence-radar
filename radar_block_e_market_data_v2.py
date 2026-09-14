"""Block E v2 — provider chain with safe Stooq daily fallback.

Yahoo query1/query2 are intraday quote providers. Stooq is deliberately used only as
an analytical daily fallback: its daily close can never become PAPER-execution eligible.
REAL_TRADING remains false.
"""
from __future__ import annotations

import csv
import io
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable

import radar_core as core
import radar_block_e_market_data_v1 as v1
from radar_block_e_market_data_v1 import *  # noqa: F401,F403

REAL_TRADING=False


def stooq_daily_mark(symbol: str, host: str='stooq.com', *, now: datetime | None=None) -> MarketQuote:
    now=v1._utc(now or datetime.now(timezone.utc))
    code=STOOQ_CODES.get(symbol.upper(), symbol.lower()+'.us')
    url=f'https://{host}/q/d/l/?s={urllib.parse.quote(code)}&i=d'
    text=core.fetch(url,20,{'User-Agent':core.BROWSER_UA,'Accept':'text/csv,text/plain,*/*'})
    rows=list(csv.DictReader(io.StringIO(text)))
    usable=[r for r in rows if r.get('Date') and r.get('Close') not in (None,'','N/D','-')]
    if not usable:
        raise RuntimeError('NO_QUOTE: empty Stooq daily history')
    row=usable[-1]
    close=float(row['Close'])
    vol=row.get('Volume')
    market_ts=f"{row['Date']}T00:00:00+00:00"
    return MarketQuote(
        symbol=symbol.upper(),price=close,market_timestamp=v1._iso(market_ts),
        provider=f'StooqDaily:{host}',provider_status='OK',currency='USD',market_state='UNKNOWN',
        volume=float(vol) if vol not in (None,'','N/D','-') else None,
        ingestion_timestamp=v1._iso(now),source_kind='FALLBACK_DAILY',
    )


def fetch_best_quote(symbol: str, *, now: datetime | None=None,
                     providers: list[tuple[str,Callable[...,MarketQuote]]] | None=None) -> dict[str,Any]:
    now=v1._utc(now or datetime.now(timezone.utc)); attempts=[]
    chain=providers or [
        ('Yahoo query1',lambda s,now=None:yahoo_chart_quote(s,'query1.finance.yahoo.com',now=now)),
        ('Yahoo query2',lambda s,now=None:yahoo_chart_quote(s,'query2.finance.yahoo.com',now=now)),
        ('Stooq daily .com',lambda s,now=None:stooq_daily_mark(s,'stooq.com',now=now)),
        ('Stooq daily .pl',lambda s,now=None:stooq_daily_mark(s,'stooq.pl',now=now)),
    ]
    for name,fn in chain:
        try:
            quote=fn(symbol,now=now); gate=market_data_gate(quote,now=now)
            attempts.append({'provider':name,'status':'OK','selected':True,'gate':gate})
            return {'status':'QUOTE_SELECTED','quote':quote.dict(),'gate':gate,'attempts':attempts,
                    'fallback_used':len(attempts)>1,'real_trading':False}
        except Exception as exc:
            attempts.append({'provider':name,'status':classify_provider_exception(exc),
                             'error':str(exc)[:240],'selected':False})
    return {'status':'NO_VALID_PROVIDER','quote':None,'gate':None,'attempts':attempts,
            'fallback_used':len(attempts)>1,'real_trading':False}


def deterministic_block_e_validation() -> dict[str,Any]:
    out=v1.deterministic_block_e_validation()
    out['provider_chain_version']='E_PROVIDER_CHAIN_V2'
    out['stooq_policy']='DAILY_ANALYTICAL_FALLBACK_NOT_EXECUTABLE'
    out['real_trading']=False
    return out


def live_block_e_probe(symbols: tuple[str,...]=('MSFT','NVDA','GOOGL','SPY','AAPL')) -> dict[str,Any]:
    rows={}; selected=0; executable=0
    for symbol in symbols:
        result=fetch_best_quote(symbol); rows[symbol]=result
        if result.get('quote'): selected+=1
        if (result.get('gate') or {}).get('paper_execution_eligible'): executable+=1
    return {'status':'PASS' if selected==len(symbols) else 'PARTIAL','symbols':rows,
            'selected_quotes':selected,'requested':len(symbols),'paper_execution_eligible':executable,
            'market_data_test_set':'READY' if selected==len(symbols) else 'PARTIAL',
            'provider_chain_version':'E_PROVIDER_CHAIN_V2',
            'broker_connected':False,'live_execution_allowed':False,'real_trading':False}
