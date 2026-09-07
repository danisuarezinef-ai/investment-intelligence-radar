import json
import radar_core as rc


def test_quote_yahoo_uses_chart_payload(monkeypatch):
    payload={
        'chart':{'result':[{
            'meta':{'regularMarketPrice':123.45},
            'indicators':{'quote':[{'close':[120.0,123.45],'volume':[100,200]}]}
        }]}
    }
    monkeypatch.setattr(rc,'fetch',lambda *a,**k:json.dumps(payload))
    p,v,src=rc._quote_yahoo('MSFT')
    assert p==123.45
    assert v==200.0
    assert src=='Yahoo Finance'


def test_quote_stooq_parses_csv(monkeypatch):
    text='Symbol,Date,Time,Open,High,Low,Close,Volume\nMSFT.US,2026-09-07,22:00:00,500,510,499,507.25,123456\n'
    monkeypatch.setattr(rc,'fetch',lambda *a,**k:text)
    p,v,src=rc._quote_stooq('msft.us')
    assert p==507.25
    assert v==123456.0
    assert src=='Stooq Quote'


def test_history_yahoo_parses_rows(monkeypatch):
    payload={
        'chart':{'result':[{
            'timestamp':[1757203200,1757289600],
            'indicators':{'quote':[{'close':[100.0,101.5],'volume':[1000,1100]}]}
        }]}
    }
    monkeypatch.setattr(rc,'fetch',lambda *a,**k:json.dumps(payload))
    rows=rc._history_yahoo('MSFT',30)
    assert len(rows)==2
    assert rows[-1][1]==101.5
    assert rows[-1][2]==1100.0
