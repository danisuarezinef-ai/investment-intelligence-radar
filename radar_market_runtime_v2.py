"""Instrumented market runtime with observed provider-attempt telemetry and circuit breaking.

All state is derived from actual provider calls. Open circuits suppress calls until
cooldown expires. No provider success is fabricated. REAL_TRADING remains false.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

import radar_core as core
from radar_provider_resilience_v1 import DEFAULT_POLICY

REAL_TRADING = False
PROVIDERS = (
    ('Yahoo query1', 'quote', lambda s, c: core._quote_yahoo(s, 'query1.finance.yahoo.com')),
    ('Yahoo query2', 'quote', lambda s, c: core._quote_yahoo(s, 'query2.finance.yahoo.com')),
    ('Stooq.com', 'quote', lambda s, c: core._quote_stooq(c, 'stooq.com')),
    ('Stooq.pl', 'quote', lambda s, c: core._quote_stooq(c, 'stooq.pl')),
    ('Stooq.com daily', 'history_fallback', lambda s, c: _latest_stooq_daily(c, 'stooq.com')),
    ('Stooq.pl daily', 'history_fallback', lambda s, c: _latest_stooq_daily(c, 'stooq.pl')),
)


def _latest_stooq_daily(code: str, host: str):
    rows = core._history_stooq(code, 10, host)
    _, price, volume = rows[-1]
    return float(price), volume, 'Stooq Daily'


def _init_tables() -> None:
    core.init_db(); c = core.con()
    c.execute('''create table if not exists provider_attempts(
        id integer primary key, ts text not null, symbol text not null, provider text not null,
        attempt_kind text not null, success integer not null, latency_ms real,
        error text, selected integer not null default 0)''')
    c.execute('''create table if not exists provider_health_state(
        provider text primary key, calls integer not null default 0, failures integer not null default 0,
        consecutive_failures integer not null default 0, last_success_at text, last_failure_at text,
        circuit_open_until real, updated_at text not null)''')
    c.execute('create index if not exists idx_provider_attempts_ts on provider_attempts(ts)')
    c.execute('create index if not exists idx_provider_attempts_provider on provider_attempts(provider,ts)')
    c.commit(); c.close()


def _health(provider: str) -> dict[str, Any]:
    _init_tables(); c = core.con()
    row = c.execute('select calls,failures,consecutive_failures,last_success_at,last_failure_at,circuit_open_until from provider_health_state where provider=?',(provider,)).fetchone()
    c.close()
    if not row:
        return {'provider':provider,'calls':0,'failures':0,'consecutive_failures':0,'last_success_at':None,'last_failure_at':None,'circuit_open_until':None}
    return {'provider':provider,'calls':int(row[0]),'failures':int(row[1]),'consecutive_failures':int(row[2]),'last_success_at':row[3],'last_failure_at':row[4],'circuit_open_until':row[5]}


def _circuit_open(provider: str, now_epoch: float | None = None) -> bool:
    state = _health(provider); until = state.get('circuit_open_until')
    return bool(until and float(until) > float(now_epoch if now_epoch is not None else time.time()))


def _record(provider: str, symbol: str, kind: str, success: bool, latency_ms: float,
            error: str | None = None, selected: bool = False) -> None:
    _init_tables(); stamp = core.now(); c = core.con()
    c.execute('insert into provider_attempts(ts,symbol,provider,attempt_kind,success,latency_ms,error,selected) values(?,?,?,?,?,?,?,?)',
              (stamp,symbol,provider,kind,1 if success else 0,float(latency_ms),error[:500] if error else None,1 if selected else 0))
    row = c.execute('select calls,failures,consecutive_failures from provider_health_state where provider=?',(provider,)).fetchone()
    calls = (int(row[0]) if row else 0) + 1
    failures = (int(row[1]) if row else 0) + (0 if success else 1)
    consecutive = 0 if success else (int(row[2]) if row else 0) + 1
    open_until = None
    if not success and consecutive >= int(DEFAULT_POLICY['failure_threshold']):
        open_until = time.time() + float(DEFAULT_POLICY['cooldown_seconds'])
    c.execute('''insert into provider_health_state(provider,calls,failures,consecutive_failures,last_success_at,last_failure_at,circuit_open_until,updated_at)
      values(?,?,?,?,?,?,?,?) on conflict(provider) do update set calls=excluded.calls,failures=excluded.failures,
      consecutive_failures=excluded.consecutive_failures,last_success_at=excluded.last_success_at,
      last_failure_at=excluded.last_failure_at,circuit_open_until=excluded.circuit_open_until,updated_at=excluded.updated_at''',
      (provider,calls,failures,consecutive,stamp if success else (_health(provider).get('last_success_at')),
       stamp if not success else (_health(provider).get('last_failure_at')),open_until,stamp))
    c.commit(); c.close()


def _mark_selected(attempt_id: int) -> None:
    c = core.con(); c.execute('update provider_attempts set selected=1 where id=?',(attempt_id,)); c.commit(); c.close()


def collect_market() -> int:
    """Collect all configured assets using live provider health and persisted circuit state."""
    _init_tables(); ok = 0; errs: list[str] = []; sources: dict[str,int] = {}
    for symbol, code in core.ASSETS.items():
        value = None; selected_attempt = None; failures = []
        for provider, kind, fn in PROVIDERS:
            if _circuit_open(provider):
                failures.append(provider+': circuit open')
                continue
            started = time.perf_counter()
            try:
                result = fn(symbol, code)
                latency = (time.perf_counter()-started)*1000.0
                _record(provider,symbol,kind,True,latency)
                c = core.con(); selected_attempt = c.execute('select max(id) from provider_attempts').fetchone()[0]; c.close()
                value = result
                break
            except Exception as exc:
                latency = (time.perf_counter()-started)*1000.0
                _record(provider,symbol,kind,False,latency,str(exc))
                failures.append(provider+': '+str(exc))
        if value is None:
            errs.append(symbol+': '+' | '.join(failures)[:700])
            continue
        if selected_attempt is not None:
            _mark_selected(int(selected_attempt))
        price, volume, source = value
        c = core.con(); c.execute('insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)',(core.now(),symbol,float(price),volume,source)); c.commit(); c.close()
        ok += 1; sources[source] = sources.get(source,0)+1
    status = 'OK' if ok else 'ERROR'; detail = f'{ok}/{len(core.ASSETS)} precios guardados'
    if sources: detail += ' · '+', '.join(f'{k} {v}' for k,v in sources.items())
    if errs: detail += ' · errores: '+'; '.join(errs[:2])
    core.log('market',status,detail)
    core.write_status(market_status=status,market_source=', '.join(sources) or 'sin fuente',prices_added=ok,last_market_errors=errs[:6])
    return ok


def provider_telemetry(window_hours: int = 24) -> dict[str, Any]:
    _init_tables(); cutoff = datetime.fromtimestamp(time.time()-max(1,window_hours)*3600,timezone.utc).isoformat(); c=core.con()
    rows = c.execute('select provider,count(*),sum(case when success=0 then 1 else 0 end),sum(case when selected=1 then 1 else 0 end),avg(latency_ms),max(ts) from provider_attempts where ts>=? group by provider order by provider',(cutoff,)).fetchall()
    latest = c.execute('select ts,symbol,provider,attempt_kind,success,latency_ms,error,selected from provider_attempts order by id desc limit 100').fetchall(); c.close()
    providers=[]
    for p,calls,failures,selected,latency,last_ts in rows:
        state=_health(p); open_now=_circuit_open(p)
        providers.append({'name':p,'calls':int(calls or 0),'failures':int(failures or 0),'selected':int(selected or 0),
                          'error_rate':(float(failures or 0)/float(calls)) if calls else None,'avg_latency_ms':float(latency) if latency is not None else None,
                          'consecutive_failures':state['consecutive_failures'],'circuit_open':open_now,
                          'circuit_open_until':state['circuit_open_until'],'last_success_at':state['last_success_at'],
                          'last_failure_at':state['last_failure_at'],'last_attempt_at':last_ts})
    attempts=[{'ts':r[0],'symbol':r[1],'provider':r[2],'kind':r[3],'success':bool(r[4]),'latency_ms':r[5],'error':r[6],'selected':bool(r[7])} for r in latest]
    fallback_observed=any(a['selected'] and a['provider'] not in ('Yahoo query1','Yahoo query2') for a in attempts)
    return {'window_hours':window_hours,'providers':providers,'recent_attempts':attempts,
            'provider_attempt_telemetry':'LIVE_OBSERVED_ATTEMPTS','circuit_breaker':'LIVE_PERSISTED_STATE',
            'failover_activation_verified':fallback_observed,'can_trade':False,'real_trading':False}
