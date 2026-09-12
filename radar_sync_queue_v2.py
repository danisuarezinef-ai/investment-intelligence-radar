"""Durable bounded retry queue for external sync operations.

Queueing is transport infrastructure only; it cannot authorize trades or releases.
"""
from __future__ import annotations
import hashlib,json,os,sqlite3,time
from pathlib import Path

REAL_TRADING=False
MAX_ATTEMPTS=6

class DurableSyncQueue:
    def __init__(self,path:str|None=None,max_attempts=MAX_ATTEMPTS):
        root=os.getenv('RADAR_USER_DATA_DIR') or os.getenv('RADAR_DATA_DIR')
        self.path=Path(path) if path else (Path(root)/'sync_retry_v2.sqlite3' if root else Path('.radar-data/sync_retry_v2.sqlite3'))
        self.path.parent.mkdir(parents=True,exist_ok=True);self.max_attempts=max(1,min(20,int(max_attempts)));self._init()
    def _db(self):
        db=sqlite3.connect(self.path);db.row_factory=sqlite3.Row;return db
    def _init(self):
        with self._db() as db:
            db.execute('create table if not exists retry_queue (id text primary key, channel text not null, payload text not null, attempts integer not null default 0, next_epoch real not null default 0, last_error text, created_epoch real not null)')
            db.execute('create table if not exists dead_letter (id text primary key, channel text not null, payload text not null, attempts integer not null, last_error text, dead_epoch real not null)')
    @staticmethod
    def key(channel,payload):
        raw=json.dumps({'channel':channel,'payload':payload},sort_keys=True,separators=(',',':'),default=str).encode();return hashlib.sha256(raw).hexdigest()
    def enqueue(self,channel,payload):
        key=self.key(channel,payload);raw=json.dumps(payload,sort_keys=True,separators=(',',':'),default=str)
        with self._db() as db:db.execute('insert or ignore into retry_queue(id,channel,payload,created_epoch) values(?,?,?,?)',(key,str(channel),raw,time.time()))
        return key
    def due(self,limit=100):
        with self._db() as db:
            rows=db.execute('select * from retry_queue where next_epoch<=? order by created_epoch limit ?',(time.time(),max(1,min(500,int(limit))))).fetchall()
        return [dict(r) for r in rows]
    def acknowledge(self,key):
        with self._db() as db:db.execute('delete from retry_queue where id=?',(str(key),))
    def fail(self,key,error,retry_after_seconds=5.0):
        with self._db() as db:
            row=db.execute('select * from retry_queue where id=?',(str(key),)).fetchone()
            if not row:return 'MISSING'
            attempts=int(row['attempts'])+1
            if attempts>=self.max_attempts:
                db.execute('insert or replace into dead_letter(id,channel,payload,attempts,last_error,dead_epoch) values(?,?,?,?,?,?)',(row['id'],row['channel'],row['payload'],attempts,str(error)[:700],time.time()))
                db.execute('delete from retry_queue where id=?',(row['id'],));return 'DEAD_LETTER'
            delay=max(1.0,min(3600.0,float(retry_after_seconds)*(2**max(0,attempts-1))))
            db.execute('update retry_queue set attempts=?,next_epoch=?,last_error=? where id=?',(attempts,time.time()+delay,str(error)[:700],row['id']));return 'RETRY'
    def stats(self):
        with self._db() as db:
            q=db.execute('select count(*) from retry_queue').fetchone()[0];d=db.execute('select count(*) from dead_letter').fetchone()[0]
        return {'queued':q,'dead_letter':d,'durable':True,'max_attempts':self.max_attempts,'ack_after_remote_success':True,'real_trading':False}

def queue_contract():
    return {'durable':True,'max_attempts':MAX_ATTEMPTS,'dead_letter':True,'ack_after_remote_success':True,'idempotency_key':'sha256(channel+payload)','real_trading':False}
