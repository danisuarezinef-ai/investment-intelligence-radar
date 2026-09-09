"""Point-in-time fundamentals evidence from SEC Company Facts.

Only values actually filed by the issuer and known by the filing date are persisted.
Unsupported/non-US assets stay explicitly missing. No synthetic fundamentals.
"""
from __future__ import annotations

import json
from typing import Any

import radar_core as core

REAL_TRADING=False
SEC_CIK={
    'MSFT':'0000789019','NVDA':'0001045810','GOOGL':'0001652044','AMZN':'0001018724',
    'META':'0001326801','AVGO':'0001730168','LLY':'0000059478','V':'0001403161',
    'BRK-B':'0001067983',
}
TAGS={
    'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','SalesRevenueNet','Revenues'],
    'operating_income':['OperatingIncomeLoss'],
    'operating_cash_flow':['NetCashProvidedByUsedInOperatingActivities'],
    'capex':['PaymentsToAcquirePropertyPlantAndEquipment'],
    'cash':['CashAndCashEquivalentsAtCarryingValue','CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'],
    'debt':['LongTermDebtAndFinanceLeaseObligationsCurrent','LongTermDebtCurrent','LongTermDebtNoncurrent','LongTermDebt'],
    'shares':['EntityCommonStockSharesOutstanding','CommonStocksIncludingAdditionalPaidInCapitalMember'],
}


def _init_table():
    core.init_db(); c=core.con()
    c.execute('''create table if not exists fundamental_snapshots(
      id integer primary key, symbol text not null, known_at text not null, period_end text,
      source text not null, payload text not null, unique(symbol,known_at,source))''')
    c.execute('create index if not exists idx_fundamental_symbol_known on fundamental_snapshots(symbol,known_at)')
    c.commit(); c.close()


def _units_for(facts:dict[str,Any], tag:str):
    item=(facts.get('us-gaap') or {}).get(tag) or (facts.get('dei') or {}).get(tag) or {}
    units=item.get('units') or {}
    out=[]
    for rows in units.values():
        if isinstance(rows,list): out.extend(x for x in rows if isinstance(x,dict))
    return out


def _latest_fact(facts:dict[str,Any], tags:list[str], *, instant:bool|None=None):
    candidates=[]
    for tag in tags:
        for row in _units_for(facts,tag):
            if row.get('val') is None or not row.get('filed'): continue
            start=row.get('start'); end=row.get('end')
            is_instant=not bool(start)
            if instant is not None and is_instant!=instant: continue
            form=str(row.get('form') or '')
            if form not in ('10-K','10-Q','20-F','40-F'): continue
            candidates.append({**row,'tag':tag})
    if not candidates:return None
    candidates.sort(key=lambda x:(str(x.get('filed')),str(x.get('end') or '')),reverse=True)
    return candidates[0]


def _annual_or_ttm_pair(facts:dict[str,Any], tags:list[str]):
    rows=[]
    for tag in tags:
        for row in _units_for(facts,tag):
            if row.get('val') is None or not row.get('filed') or not row.get('start') or not row.get('end'):continue
            if str(row.get('form') or '') not in ('10-K','10-Q'):continue
            try:
                from datetime import date
                days=(date.fromisoformat(str(row['end'])[:10])-date.fromisoformat(str(row['start'])[:10])).days
            except Exception:days=0
            if days>=250:rows.append({**row,'tag':tag,'days':days})
    rows.sort(key=lambda x:(str(x.get('filed')),str(x.get('end'))),reverse=True)
    return rows[:2]


def _safe_float(x):
    try:return float(x)
    except Exception:return None


def _build_payload(symbol:str,data:dict[str,Any])->dict[str,Any]:
    facts=data.get('facts') or {}
    revs=_annual_or_ttm_pair(facts,TAGS['revenue'])
    revenue=_safe_float(revs[0]['val']) if revs else None
    prior_revenue=_safe_float(revs[1]['val']) if len(revs)>1 else None
    revenue_growth=((revenue/prior_revenue)-1.0) if revenue is not None and prior_revenue not in (None,0) else None
    op=_latest_fact(facts,TAGS['operating_income'],instant=False); opv=_safe_float(op.get('val')) if op else None
    ocf=_latest_fact(facts,TAGS['operating_cash_flow'],instant=False); ocfv=_safe_float(ocf.get('val')) if ocf else None
    capex=_latest_fact(facts,TAGS['capex'],instant=False); capexv=_safe_float(capex.get('val')) if capex else None
    cash=_latest_fact(facts,TAGS['cash'],instant=True); cashv=_safe_float(cash.get('val')) if cash else None
    debt_rows=[]
    for tag in TAGS['debt']:
        r=_latest_fact(facts,[tag],instant=True)
        if r and _safe_float(r.get('val')) is not None: debt_rows.append(r)
    debt=sum(float(r['val']) for r in debt_rows) if debt_rows else None
    shares=_latest_fact(facts,TAGS['shares'],instant=True); sharesv=_safe_float(shares.get('val')) if shares else None
    known=[str(x.get('filed')) for x in ([op,ocf,capex,cash,shares]+debt_rows+revs[:1]) if isinstance(x,dict) and x.get('filed')]
    known_at=max(known) if known else None
    period=[str(x.get('end')) for x in ([op,ocf,capex,cash,shares]+debt_rows+revs[:1]) if isinstance(x,dict) and x.get('end')]
    period_end=max(period) if period else None
    return {
      'symbol':symbol,'known_at':known_at,'period_end':period_end,
      'revenue':revenue,'prior_revenue':prior_revenue,'revenue_growth':revenue_growth,
      'operating_income':opv,'operating_margin':(opv/revenue if opv is not None and revenue not in (None,0) else None),
      'operating_cash_flow':ocfv,'capex':capexv,'free_cash_flow':(ocfv-capexv if ocfv is not None and capexv is not None else None),
      'cash':cashv,'debt':debt,'net_debt':(debt-cashv if debt is not None and cashv is not None else None),
      'shares_outstanding':sharesv,'source':'SEC_COMPANYFACTS_POINT_IN_TIME','real_trading':False,
    }


def collect_fundamentals()->dict[str,Any]:
    _init_table(); stored=0; failures=[]; unsupported=[s for s in core.ASSETS if s not in SEC_CIK]
    for symbol,cik in SEC_CIK.items():
        try:
            raw=core.fetch(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json',25,{'Accept-Encoding':'identity','User-Agent':core.UA})
            payload=_build_payload(symbol,json.loads(raw))
            if not payload.get('known_at'):
                failures.append(symbol+': no filed facts');continue
            c=core.con();c.execute('insert or ignore into fundamental_snapshots(symbol,known_at,period_end,source,payload) values(?,?,?,?,?)',
              (symbol,payload['known_at'],payload.get('period_end'),payload['source'],json.dumps(payload,ensure_ascii=False)));stored+=c.total_changes;c.commit();c.close()
        except Exception as exc:failures.append(symbol+': '+str(exc)[:300])
    core.log('fundamentals','OK' if stored or not failures else 'ERROR',f'{stored} snapshots nuevos · unsupported={len(unsupported)}'+((' · '+failures[0]) if failures else ''))
    return {'stored':stored,'supported_symbols':sorted(SEC_CIK),'unsupported_symbols':unsupported,'failures':failures[:10],
            'source':'SEC_COMPANYFACTS_POINT_IN_TIME','can_trade':False,'real_trading':False}


def latest_fundamental(symbol:str)->dict[str,Any]|None:
    _init_table();c=core.con();row=c.execute('select payload from fundamental_snapshots where symbol=? order by known_at desc,id desc limit 1',(symbol,)).fetchone();c.close()
    if not row:return None
    try:return json.loads(row[0])
    except Exception:return None


def fundamental_coverage()->dict[str,Any]:
    _init_table(); rows=[]
    for symbol in core.ASSETS:
        p=latest_fundamental(symbol)
        rows.append({'symbol':symbol,'available':bool(p),'known_at':p.get('known_at') if p else None,'period_end':p.get('period_end') if p else None,
                     'source':p.get('source') if p else None,'valuation_multiple_available':False})
    return {'assets_expected':len(core.ASSETS),'fundamentals_observed':sum(1 for x in rows if x['available']),
            'assets':rows,'valuation_multiple':'NOT_YET_DERIVED_WITH_VERIFIED_MARKET_CAP','can_trade':False,'real_trading':False}
