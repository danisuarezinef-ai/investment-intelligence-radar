"""Investment Memory v5: append-only PIT journal and forward evidence engine."""
from __future__ import annotations
import hashlib,json,os
from datetime import datetime,timezone,timedelta

REAL_TRADING=False
HORIZON_DAYS={'1d':1,'1w':5,'1m':21,'3m':63}
THESIS_STATES=('NEW','ACTIVE','STRENGTHENED','WEAKENED','INVALIDATED','CLOSED')

def utcnow():return datetime.now(timezone.utc).isoformat()
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),default=str)
def digest(x):return hashlib.sha256(canon(x).encode()).hexdigest()
def _dt(x):return datetime.fromisoformat(str(x).replace('Z','+00:00')).astimezone(timezone.utc)

def market_target(created_at,horizon):
    """Weekday-safe target. Exchange holidays remain an explicit external limitation."""
    if horizon not in HORIZON_DAYS:raise ValueError('unsupported horizon')
    d=_dt(created_at);left=HORIZON_DAYS[horizon]
    while left:
        d+=timedelta(days=1)
        if d.weekday()<5:left-=1
    return d.isoformat()

def init_memory(db):
 c=db.cursor();c.executescript('''
 CREATE TABLE IF NOT EXISTS prediction_ledger(
  id TEXT PRIMARY KEY,origin_node TEXT NOT NULL,origin_id TEXT NOT NULL,created_at TEXT NOT NULL,
  target_date TEXT NOT NULL,asset TEXT NOT NULL,horizon TEXT NOT NULL,model_version TEXT NOT NULL,
  prediction_hash TEXT NOT NULL UNIQUE,feature_fingerprint TEXT NOT NULL,thesis_fingerprint TEXT NOT NULL,
  confidence REAL NOT NULL,uncertainty TEXT NOT NULL,decision_state TEXT NOT NULL,paper_allocation TEXT,
  data_cutoff TEXT NOT NULL,known_at_boundary TEXT NOT NULL,provenance_snapshot TEXT NOT NULL,payload TEXT NOT NULL,
  outcome TEXT,evaluated_at TEXT,UNIQUE(origin_node,origin_id));
 CREATE TABLE IF NOT EXISTS thesis_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,origin_node TEXT NOT NULL,origin_id TEXT NOT NULL,
  event_time TEXT NOT NULL,thesis_id TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,
  event_hash TEXT NOT NULL UNIQUE,UNIQUE(origin_node,origin_id));
 CREATE TABLE IF NOT EXISTS decision_journal(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,prediction_id TEXT,action TEXT NOT NULL,thesis_hash TEXT,uncertainty TEXT,allocation TEXT,reason TEXT,payload_hash TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS failure_memory(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,prediction_id TEXT,pattern TEXT NOT NULL,cost REAL DEFAULT 0,regime TEXT,horizon TEXT,evidence TEXT);
 CREATE TABLE IF NOT EXISTS signal_value(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,signal TEXT NOT NULL,horizon TEXT,regime TEXT,full_objective REAL,ablated_objective REAL,marginal_value REAL);
 CREATE TRIGGER IF NOT EXISTS prediction_core_immutable BEFORE UPDATE ON prediction_ledger
 WHEN NEW.id<>OLD.id OR NEW.origin_node<>OLD.origin_node OR NEW.origin_id<>OLD.origin_id OR
 NEW.created_at<>OLD.created_at OR NEW.target_date<>OLD.target_date OR NEW.asset<>OLD.asset OR
 NEW.horizon<>OLD.horizon OR NEW.model_version<>OLD.model_version OR NEW.prediction_hash<>OLD.prediction_hash OR
 NEW.feature_fingerprint<>OLD.feature_fingerprint OR NEW.thesis_fingerprint<>OLD.thesis_fingerprint OR
 NEW.confidence<>OLD.confidence OR NEW.uncertainty<>OLD.uncertainty OR NEW.decision_state<>OLD.decision_state OR
 coalesce(NEW.paper_allocation,'')<>coalesce(OLD.paper_allocation,'') OR NEW.data_cutoff<>OLD.data_cutoff OR
 NEW.known_at_boundary<>OLD.known_at_boundary OR NEW.provenance_snapshot<>OLD.provenance_snapshot OR NEW.payload<>OLD.payload
 BEGIN SELECT RAISE(ABORT,'forward prediction is immutable');END;
 CREATE TRIGGER IF NOT EXISTS prediction_outcome_single_assignment BEFORE UPDATE OF outcome ON prediction_ledger
 WHEN OLD.outcome IS NOT NULL BEGIN SELECT RAISE(ABORT,'outcome already assigned');END;
 CREATE TRIGGER IF NOT EXISTS thesis_events_no_update BEFORE UPDATE ON thesis_events BEGIN SELECT RAISE(ABORT,'thesis history is append-only');END;
 CREATE TRIGGER IF NOT EXISTS thesis_events_no_delete BEFORE DELETE ON thesis_events BEGIN SELECT RAISE(ABORT,'thesis history is append-only');END;
 ''');db.commit()

def freeze_prediction(db,p,origin_node='cloud-primary',origin_id=None,clock=None):
 init_memory(db);p=dict(p);created=(clock or utcnow)()
 # Caller timestamps are never authoritative; rejecting them prevents backfill/backdating.
 if p.get('created_at') and abs((_dt(p['created_at'])-_dt(created)).total_seconds())>60:raise ValueError('forward ledger forbids backdating')
 p['created_at']=created;p['asset']=p.get('asset') or p.get('symbol');p['target_date']=p.get('target_date') or market_target(created,p['horizon'])
 if not p.get('asset') or not p.get('model_version'):raise ValueError('asset and model_version required')
 cutoff=p.get('data_cutoff') or created;known=p.get('known_at_boundary') or cutoff
 if _dt(cutoff)>_dt(created) or _dt(known)>_dt(created):raise ValueError('known_at/data_cutoff cannot be in the future')
 if _dt(p['target_date'])<=_dt(created):raise ValueError('target_date must be future')
 features=p.get('features') or {};thesis=p.get('thesis') or '';provenance=p.get('provenance_snapshot') or {}
 if provenance.get('lookahead') is not False:raise ValueError('lookahead=false provenance required')
 p.update(real_trading=False,immutable=True,data_cutoff=cutoff,known_at_boundary=known)
 ff=digest(features);tf=digest(thesis);prediction_hash=digest(p);pid=p.get('prediction_id') or prediction_hash[:24];oid=str(origin_id or pid)
 db.execute('''INSERT INTO prediction_ledger(id,origin_node,origin_id,created_at,target_date,asset,horizon,
  model_version,prediction_hash,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,
  decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot,payload,outcome,evaluated_at)
  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL)''',
  (pid,origin_node,oid,created,p['target_date'],p['asset'],p['horizon'],p['model_version'],prediction_hash,ff,tf,float(p.get('confidence',0)),canon(p.get('uncertainty') or {}),p.get('decision_state','WAIT'),canon(p.get('paper_allocation')) if p.get('paper_allocation') is not None else None,cutoff,known,canon(provenance),canon(p)))
 db.commit();return pid

def evaluate_prediction(db,prediction_id,outcome,evaluated_at=None):
 init_memory(db);row=db.execute('SELECT target_date,outcome FROM prediction_ledger WHERE id=?',(prediction_id,)).fetchone()
 if not row:raise KeyError(prediction_id)
 if row[1] is not None:raise ValueError('immutable outcome already recorded')
 stamp=evaluated_at or utcnow()
 if _dt(stamp)<_dt(row[0]):raise ValueError('outcome cannot be assigned before maturity')
 cur=db.execute('UPDATE prediction_ledger SET outcome=?,evaluated_at=? WHERE id=? AND outcome IS NULL',(canon(outcome),stamp,prediction_id))
 if cur.rowcount!=1:raise ValueError('outcome assignment conflict')
 db.commit()

def append_thesis_event(db,thesis_id,state,payload,origin_node='cloud-primary',origin_id=None,event_time=None):
 init_memory(db)
 if state not in THESIS_STATES:raise ValueError('invalid thesis state')
 last=db.execute('SELECT state FROM thesis_events WHERE thesis_id=? ORDER BY id DESC LIMIT 1',(thesis_id,)).fetchone()
 allowed={None:{'NEW'},'NEW':{'ACTIVE','CLOSED'},'ACTIVE':{'STRENGTHENED','WEAKENED','INVALIDATED','CLOSED'},'STRENGTHENED':{'WEAKENED','INVALIDATED','CLOSED'},'WEAKENED':{'STRENGTHENED','INVALIDATED','CLOSED'},'INVALIDATED':{'CLOSED'},'CLOSED':set()}
 if state not in allowed[last[0] if last else None]:raise ValueError('invalid thesis transition')
 stamp=event_time or utcnow();body={'thesis_id':thesis_id,'state':state,'payload':payload,'event_time':stamp};h=digest(body);oid=str(origin_id or h[:24])
 db.execute('INSERT INTO thesis_events(origin_node,origin_id,event_time,thesis_id,state,payload,event_hash) VALUES(?,?,?,?,?,?,?)',(origin_node,oid,stamp,thesis_id,state,canon(payload),h));db.commit();return h

def record_decision(db,prediction_id,action,thesis_hash,uncertainty,allocation,reason):
 init_memory(db);body={'prediction_id':prediction_id,'action':action,'thesis_hash':thesis_hash,'uncertainty':uncertainty,'allocation':allocation,'reason':reason,'real_trading':False};did=digest(body)[:24]
 db.execute('INSERT OR IGNORE INTO decision_journal VALUES(?,?,?,?,?,?,?,?,?)',(did,utcnow(),prediction_id,action,thesis_hash,canon(uncertainty),canon(allocation),reason,digest(body)));db.commit();return did

def ledger_status(db):
 init_memory(db);row=db.execute('select count(*),min(created_at),sum(case when outcome is not null then 1 else 0 end) from prediction_ledger').fetchone()
 return {'predictions':row[0],'first_forward_timestamp':row[1],'matured':row[2] or 0,'real_trading':False}
