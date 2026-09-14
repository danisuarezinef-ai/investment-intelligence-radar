"""Block E — authoritative PAPER market-data layer.

Goals:
- distinguish provider failure / no quote / market closed / stale data;
- preserve provider market timestamp rather than pretending ingestion time is quote time;
- freeze a liquid initial PAPER universe with a reproducible hash;
- provide primary+fallback quotes and a strict execution gate;
- normalize corporate actions without rewriting raw observations.

This module cannot place broker orders. REAL_TRADING is permanently false.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import urllib.error
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Callable

import radar_core as core

REAL_TRADING = False
QUOTE_FRESHNESS_SECONDS = 120
CLOSED_MARK_ANALYSIS_MAX_SECONDS = 72 * 3600

# Frozen development universe: highly liquid equities + broad/risk-regime ETFs.
# It is deliberately finite for the first reproducible PAPER experiments.
UNIVERSE_V1 = (
    'SPY','QQQ','IWM','DIA','TLT','GLD','HYG','EEM',
    'AAPL','MSFT','NVDA','GOOGL','AMZN','META','AVGO','AMD','TSLA',
    'JPM','BAC','V','MA','XOM','CVX','LLY','UNH','JNJ','PG','COST','WMT',
    'HD','CAT','GE','ORCL','CRM','NFLX','ADBE',
)
STOOQ_CODES = {symbol: symbol.lower().replace('.', '-') + '.us' for symbol in UNIVERSE_V1}


def _utc(value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(float(value), timezone.utc)
    else:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('naive timestamp forbidden')
    return dt.astimezone(timezone.utc)


def _iso(value: Any) -> str:
    return _utc(value).isoformat().replace('+00:00', 'Z')


def frozen_universe_v1() -> dict[str, Any]:
    members = tuple(sorted(set(UNIVERSE_V1)))
    raw = json.dumps(members, separators=(',', ':')).encode()
    return {
        'version': 'E_UNIVERSE_V1',
        'members': list(members),
        'count': len(members),
        'hash': hashlib.sha256(raw).hexdigest(),
        'selection': 'liquid_US_equities_and_regime_ETFs',
        'frozen': True,
        'can_trade': False,
        'real_trading': False,
    }


@dataclass(frozen=True)
class MarketQuote:
    symbol: str
    price: float
    market_timestamp: str
    provider: str
    provider_status: str
    currency: str
    market_state: str = 'UNKNOWN'
    bid: float | None = None
    ask: float | None = None
    volume: float | None = None
    ingestion_timestamp: str | None = None
    source_kind: str = 'QUOTE'

    def dict(self) -> dict[str, Any]:
        return asdict(self)


def _market_state_from_period(meta: dict[str, Any], now: datetime) -> str:
    periods = meta.get('currentTradingPeriod') or {}
    regular = periods.get('regular') or {}
    try:
        start = _utc(regular['start']); end = _utc(regular['end'])
        return 'OPEN' if start <= now <= end else 'CLOSED'
    except Exception:
        return 'UNKNOWN'


def yahoo_chart_quote(symbol: str, host: str = 'query1.finance.yahoo.com', *, now: datetime | None = None) -> MarketQuote:
    now = _utc(now or datetime.now(timezone.utc))
    ys = urllib.parse.quote(symbol, safe='')
    url = f'https://{host}/v8/finance/chart/{ys}?interval=1m&range=1d&includePrePost=false'
    payload = json.loads(core.fetch(url, 15, {'User-Agent': core.BROWSER_UA, 'Accept': 'application/json,*/*'}))
    chart = payload.get('chart') or {}
    if chart.get('error'):
        raise RuntimeError('NO_QUOTE: ' + str(chart.get('error')))
    results = chart.get('result') or []
    if not results:
        raise RuntimeError('NO_QUOTE: empty Yahoo chart result')
    item = results[0]; meta = item.get('meta') or {}
    quote = ((item.get('indicators') or {}).get('quote') or [{}])[0]
    stamps = item.get('timestamp') or []
    closes = quote.get('close') or []
    vols = quote.get('volume') or []
    last_index = next((i for i in range(min(len(stamps), len(closes))-1, -1, -1) if closes[i] is not None), None)
    price = meta.get('regularMarketPrice')
    market_ts = meta.get('regularMarketTime')
    volume = meta.get('regularMarketVolume')
    if last_index is not None:
        # Prefer the timestamp that actually belongs to the observed intraday bar.
        market_ts = stamps[last_index]
        if price is None:
            price = closes[last_index]
        if volume is None and last_index < len(vols):
            volume = vols[last_index]
    if price is None or market_ts is None:
        raise RuntimeError('NO_QUOTE: Yahoo price/timestamp missing')
    return MarketQuote(
        symbol=symbol.upper(), price=float(price), market_timestamp=_iso(market_ts),
        provider=f'Yahoo:{host}', provider_status='OK',
        currency=str(meta.get('currency') or 'USD').upper(),
        market_state=_market_state_from_period(meta, now),
        bid=float(meta['bid']) if meta.get('bid') is not None else None,
        ask=float(meta['ask']) if meta.get('ask') is not None else None,
        volume=float(volume) if volume is not None else None,
        ingestion_timestamp=_iso(now), source_kind='INTRADAY_QUOTE',
    )


def stooq_quote(symbol: str, host: str = 'stooq.com', *, now: datetime | None = None) -> MarketQuote:
    now = _utc(now or datetime.now(timezone.utc)); code = STOOQ_CODES.get(symbol.upper(), symbol.lower()+'.us')
    url = f'https://{host}/q/l/?s={urllib.parse.quote(code)}&f=sd2t2ohlcv&h&e=csv'
    text = core.fetch(url, 15, {'User-Agent': core.BROWSER_UA, 'Accept': 'text/csv,text/plain,*/*'})
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise RuntimeError('NO_QUOTE: empty Stooq response')
    row = rows[0]; close = row.get('Close'); date = row.get('Date'); tm = row.get('Time')
    if close in (None, '', 'N/D', '-'):
        raise RuntimeError('NO_QUOTE: Stooq price missing')
    if not date:
        raise RuntimeError('NO_QUOTE: Stooq market date missing')
    # Stooq's CSV timestamp is kept as source evidence. When timezone is not explicit,
    # it is not promoted to executable freshness; source_kind reflects that limitation.
    market_ts = f'{date}T{tm or "00:00:00"}+00:00'
    vol = row.get('Volume')
    return MarketQuote(
        symbol=symbol.upper(), price=float(close), market_timestamp=_iso(market_ts),
        provider=f'Stooq:{host}', provider_status='OK', currency='USD', market_state='UNKNOWN',
        volume=float(vol) if vol not in (None, '', 'N/D', '-') else None,
        ingestion_timestamp=_iso(now), source_kind='FALLBACK_QUOTE',
    )


def classify_provider_exception(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404: return 'PROVIDER_HTTP_404'
        if exc.code == 429: return 'PROVIDER_RATE_LIMIT'
        if 500 <= exc.code <= 599: return 'PROVIDER_5XX'
        return f'PROVIDER_HTTP_{exc.code}'
    text = str(exc).lower()
    if 'no_quote' in text or 'sin precio' in text or 'sin resultado' in text: return 'NO_QUOTE'
    if 'timed out' in text or isinstance(exc, TimeoutError): return 'PROVIDER_TIMEOUT'
    return 'PROVIDER_ERROR'


def market_data_gate(quote: MarketQuote | dict[str, Any], *, now: datetime | None = None,
                     universe: set[str] | None = None) -> dict[str, Any]:
    q = quote.dict() if isinstance(quote, MarketQuote) else dict(quote)
    now = _utc(now or datetime.now(timezone.utc)); blockers: list[str] = []
    symbol = str(q.get('symbol') or '').upper(); provider = str(q.get('provider') or '')
    status = str(q.get('provider_status') or '').upper(); currency = str(q.get('currency') or '').upper()
    state = str(q.get('market_state') or 'UNKNOWN').upper()
    allowed = universe if universe is not None else set(UNIVERSE_V1)
    try: price = float(q.get('price'))
    except Exception: price = 0.0
    if symbol not in allowed: blockers.append('symbol_not_in_frozen_universe')
    if price <= 0: blockers.append('price_nonpositive_or_missing')
    if not provider: blockers.append('provider_missing')
    if status != 'OK': blockers.append('provider_not_ok')
    if not currency: blockers.append('currency_missing')
    try:
        market_ts = _utc(q.get('market_timestamp')); age = max(0.0, (now-market_ts).total_seconds())
    except Exception:
        market_ts = None; age = None; blockers.append('market_timestamp_invalid')
    bid = q.get('bid'); ask = q.get('ask')
    if bid is not None and ask is not None:
        try:
            if float(bid) <= 0 or float(ask) <= 0 or float(bid) > float(ask): blockers.append('bid_ask_incoherent')
        except Exception: blockers.append('bid_ask_invalid')
    fresh = age is not None and age <= QUOTE_FRESHNESS_SECONDS
    analysis_valid = not blockers and (fresh or (state == 'CLOSED' and age is not None and age <= CLOSED_MARK_ANALYSIS_MAX_SECONDS))
    executable = bool(analysis_valid and fresh and state == 'OPEN' and q.get('source_kind') == 'INTRADAY_QUOTE')
    if state == 'OPEN' and not fresh: blockers.append('open_market_quote_stale')
    if state != 'OPEN': executable = False
    return {
        'symbol': symbol, 'price': price, 'market_timestamp': _iso(market_ts) if market_ts else None,
        'ingestion_timestamp': q.get('ingestion_timestamp'), 'provider': provider,
        'provider_status': status, 'currency': currency, 'market_state': state,
        'age_seconds': age, 'fresh': fresh, 'analysis_valid': analysis_valid,
        'paper_execution_eligible': executable, 'blockers': sorted(set(blockers)),
        'can_submit_broker_order': False, 'real_trading': False,
    }


def fetch_best_quote(symbol: str, *, now: datetime | None = None,
                     providers: list[tuple[str, Callable[..., MarketQuote]]] | None = None) -> dict[str, Any]:
    now = _utc(now or datetime.now(timezone.utc)); attempts = []
    chain = providers or [
        ('Yahoo query1', lambda s, now=None: yahoo_chart_quote(s, 'query1.finance.yahoo.com', now=now)),
        ('Yahoo query2', lambda s, now=None: yahoo_chart_quote(s, 'query2.finance.yahoo.com', now=now)),
        ('Stooq.com', lambda s, now=None: stooq_quote(s, 'stooq.com', now=now)),
        ('Stooq.pl', lambda s, now=None: stooq_quote(s, 'stooq.pl', now=now)),
    ]
    for name, fn in chain:
        try:
            quote = fn(symbol, now=now); gate = market_data_gate(quote, now=now)
            attempts.append({'provider': name, 'status': 'OK', 'selected': True, 'gate': gate})
            return {'status':'QUOTE_SELECTED','quote':quote.dict(),'gate':gate,'attempts':attempts,
                    'fallback_used':len(attempts)>1,'real_trading':False}
        except Exception as exc:
            attempts.append({'provider':name,'status':classify_provider_exception(exc),'error':str(exc)[:240],'selected':False})
    return {'status':'NO_VALID_PROVIDER','quote':None,'gate':None,'attempts':attempts,
            'fallback_used':len(attempts)>1,'real_trading':False}


def normalize_corporate_action(raw_price: float, action: dict[str, Any]) -> dict[str, Any]:
    """Return a derived normalized representation; raw price is never overwritten."""
    price = float(raw_price); typ = str(action.get('type') or action.get('action_type') or '').upper()
    adjusted = price; factor = 1.0; cash = 0.0; new_symbol = action.get('new_symbol')
    if typ == 'SPLIT':
        ratio = float(action.get('ratio') or 0.0)
        if ratio <= 0: raise ValueError('split ratio must be positive')
        factor = 1.0 / ratio; adjusted = price * factor
    elif typ == 'DIVIDEND':
        cash = float(action.get('cash_amount') or 0.0)
        if cash < 0: raise ValueError('dividend cannot be negative')
    elif typ in {'TICKER_CHANGE','MERGER','DELISTING','SPINOFF'}:
        pass
    else:
        raise ValueError('unsupported corporate action')
    return {'raw_price':price,'derived_adjusted_price':adjusted,'price_factor':factor,
            'cash_distribution':cash,'old_symbol':action.get('symbol'),'new_symbol':new_symbol,
            'action_type':typ,'raw_mutated':False,'real_trading':False}


def deterministic_block_e_validation() -> dict[str, Any]:
    now = datetime(2026, 9, 14, 14, 45, tzinfo=timezone.utc)
    fresh = MarketQuote('MSFT',500.0,'2026-09-14T14:44:30Z','fixture','OK','USD','OPEN',499.9,500.1,1000,_iso(now),'INTRADAY_QUOTE')
    stale = MarketQuote('NVDA',180.0,'2026-09-14T14:30:00Z','fixture','OK','USD','OPEN',None,None,None,_iso(now),'INTRADAY_QUOTE')
    closed = MarketQuote('GOOGL',210.0,'2026-09-13T20:00:00Z','fixture','OK','USD','CLOSED',None,None,None,_iso(now),'INTRADAY_QUOTE')
    f = market_data_gate(fresh,now=now); s=market_data_gate(stale,now=now); c=market_data_gate(closed,now=now)
    seq=[
      ('broken',lambda symbol,now=None: (_ for _ in ()).throw(urllib.error.HTTPError('x',404,'not found',{},None))),
      ('fallback',lambda symbol,now=None: fresh),
    ]
    fallback=fetch_best_quote('MSFT',now=now,providers=seq)
    universe=frozen_universe_v1(); split=normalize_corporate_action(100,{'type':'SPLIT','symbol':'XYZ','ratio':2})
    div=normalize_corporate_action(100,{'type':'DIVIDEND','symbol':'XYZ','cash_amount':1.25})
    checks={
      'frozen_universe_20_50':20<=universe['count']<=50,
      'universe_hash_present':len(universe['hash'])==64,
      'fresh_open_executable':f['paper_execution_eligible'] is True,
      'stale_open_rejected':s['paper_execution_eligible'] is False and 'open_market_quote_stale' in s['blockers'],
      'closed_distinct_from_failure':c['market_state']=='CLOSED' and c['provider_status']=='OK' and not c['paper_execution_eligible'],
      'http_404_falls_back':fallback['status']=='QUOTE_SELECTED' and fallback['fallback_used'] and fallback['attempts'][0]['status']=='PROVIDER_HTTP_404',
      'split_derived_not_raw_mutation':split['raw_price']==100 and split['derived_adjusted_price']==50 and not split['raw_mutated'],
      'dividend_preserved':div['cash_distribution']==1.25 and div['raw_price']==100,
      'real_trading_false':REAL_TRADING is False,
    }
    return {'status':'PASS' if all(checks.values()) else 'FAILED','checks':checks,'universe':universe,
            'market_data_test_set':'DETERMINISTIC_READY' if all(checks.values()) else 'NOT_READY',
            'external_provider_probe':'NOT_RUN','real_trading':False}


def live_block_e_probe(symbols: tuple[str,...]=('MSFT','NVDA','GOOGL','SPY','AAPL')) -> dict[str, Any]:
    rows={}; selected=0; executable=0
    for symbol in symbols:
        result=fetch_best_quote(symbol); rows[symbol]=result
        if result.get('quote'): selected += 1
        if (result.get('gate') or {}).get('paper_execution_eligible'): executable += 1
    return {'status':'PASS' if selected==len(symbols) else 'PARTIAL', 'symbols':rows,
            'selected_quotes':selected,'requested':len(symbols),'paper_execution_eligible':executable,
            'market_data_test_set':'READY' if selected==len(symbols) else 'PARTIAL',
            'broker_connected':False,'live_execution_allowed':False,'real_trading':False}
