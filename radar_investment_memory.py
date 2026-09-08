"""Investment Memory v2: immutable decision/prediction journal for forward evaluation."""
import sqlite3,json,hashlib
from datetime import datetime,timezone
REAL_TRADING=False

def utcnow():return datetime.now(timezone.utc).isoformat()
def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'))
def digest(x):return hashlib.sha256(canon(x).encode()).hexdigest()

def init_memory(db):
 c=db.cursor();c.executescript('''
 CREATE TABLE IF NOT EXISTS prediction_ledger(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,symbol TEXT NOT NULL,horizon TEXT NOT NULL,target_date TEXT NOT NULL,model_version TEXT NOT NULL,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,outcome TEXT,evaluated_at TEXT);
 CREATE TABLE IF NOT EXISTS decision_journal(id TEXT PRIMARY KEY,created_at TEXT NOT NULL,prediction_id TEXT,action TEXT NOT NULL,thesis_hash TEXT,uncertainty TEXT,allocation TEXT,reason TEXT,payload_hash TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS failure_memory(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,prediction_id TEXT,pattern TEXT NOT NULL,cost REAL DEFAULT 0,regime TEXT,horizon TEXT,evidence TEXT);
 CREATE TABLE IF NOT EXISTS signal_value(id INTEGER PRIMARY KEY AUTOINCREMENT,created_at TEXT NOT NULL,signal TEXT NOT NULL,horizon TEXT,regime TEXT,full_objective REAL,ablated_objective REAL,marginal_value REAL);
 ''');db.commit()

def freeze_prediction(db,p):
 init_memory(db);p=dict(p);p.setdefault('created_at',utcnow());p.setdefault('real_trading',False);raw=canon(p);pid=p.get('id') or digest(p)[:24]
 db.execute('INSERT INTO prediction_ledger VALUES(?,?,?,?,?,?,?,?,?,NULL)',(pid,p['created_at'],p['symbol'],p['horizon'],p['target_date'],p['model_version'],raw,digest(p),None));db.commit();return pid

def evaluate_prediction(db,prediction_id,outcome):
 row=db.execute('SELECT outcome FROM prediction_ledger WHERE id=?',(prediction_id,)).fetchone()
 if not row:raise KeyError(prediction_id)
 if row[0] is not None:raise ValueError('immutable outcome already recorded')
 db.execute('UPDATE prediction_ledger SET outcome=?,evaluated_at=? WHERE id=?',(canon(outcome),utcnow(),prediction_id));db.commit()

def record_decision(db,prediction_id,action,thesis_hash,uncertainty,allocation,reason):
 body={'prediction_id':prediction_id,'action':action,'thesis_hash':thesis_hash,'uncertainty':uncertainty,'allocation':allocation,'reason':reason,'real_trading':False};did=digest(body)[:24]
 db.execute('INSERT OR IGNORE INTO decision_journal VALUES(?,?,?,?,?,?,?,?,?)',(did,utcnow(),prediction_id,action,thesis_hash,canon(uncertainty),canon(allocation),reason,digest(body)));db.commit();return did
