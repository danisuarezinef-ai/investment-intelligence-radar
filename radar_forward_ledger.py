"""Immutable forward evidence ledger for Radar.

This module is deliberately append-only. It freezes the information available
when a prediction is made so later model versions cannot rewrite history.
"""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone, timedelta
from radar_core import con, now
from radar_learning import HORIZONS, capture_predictions

REAL_TRADING = False


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def init_forward_ledger():
    c=con()
    c.execute('''create table if not exists forward_prediction_ledger(
        prediction_id integer primary key,
        prediction_hash text not null unique,
        frozen_at text not null,
        target_at text not null,
        symbol text not null,
        horizon text not null,
        model_version text not null,
        data_cutoff text not null,
        feature_fingerprint text not null,
        thesis_fingerprint text not null,
        payload text not null,
        outcome_status text not null default 'PENDING',
        real_trading integer not null default 0
    )''')
    c.execute('create index if not exists idx_forward_target on forward_prediction_ledger(outcome_status,target_at)')
    c.commit(); c.close()


def freeze_new_predictions():
    """Capture normal predictions then append previously unseen rows to ledger."""
    init_forward_ledger(); capture_predictions(force=False)
    c=con()
    rows=c.execute('''select p.id,p.created_at,p.symbol,p.horizon,p.model_version,p.score,p.confidence,
                             p.entry_price,p.thesis,p.features,p.regime,p.source_snapshot
                      from predictions p left join forward_prediction_ledger f on f.prediction_id=p.id
                      where f.prediction_id is null order by p.id''').fetchall()
    added=0
    for r in rows:
        pid,created,symbol,horizon,version,score,confidence,entry,thesis,features,regime,sources=r
        try: feature_obj=json.loads(features or '{}')
        except Exception: feature_obj={"raw":features}
        try: source_obj=json.loads(sources or '{}')
        except Exception: source_obj={"raw":sources}
        payload={"prediction_id":pid,"created_at":created,"symbol":symbol,"horizon":horizon,
                 "model_version":version,"score":score,"confidence":confidence,"entry_price":entry,
                 "thesis":thesis,"features":feature_obj,"regime":regime,"source_snapshot":source_obj,
                 "data_cutoff":created,"real_trading":False}
        days=HORIZONS.get(horizon)
        if not days: continue
        dt=datetime.fromisoformat(str(created).replace('Z','+00:00'))
        target=(dt+timedelta(days=days)).isoformat()
        phash=_hash(payload)
        c.execute('''insert or ignore into forward_prediction_ledger(
            prediction_id,prediction_hash,frozen_at,target_at,symbol,horizon,model_version,data_cutoff,
            feature_fingerprint,thesis_fingerprint,payload,outcome_status,real_trading)
            values(?,?,?,?,?,?,?,?,?,?,?,?,0)''',
            (pid,phash,now(),target,symbol,horizon,version,created,_hash(feature_obj),_hash(thesis or ''),
             _canonical(payload),'PENDING'))
        if c.rowcount: added+=1
    c.commit(); c.close()
    return {"added":added,"real_trading":False}


def ledger_status():
    init_forward_ledger(); c=con()
    row=c.execute('''select count(*),min(frozen_at),sum(case when outcome_status='PENDING' then 1 else 0 end)
                     from forward_prediction_ledger''').fetchone()
    c.close()
    return {"predictions":int(row[0] or 0),"first_frozen_at":row[1],"pending":int(row[2] or 0),"real_trading":False}
