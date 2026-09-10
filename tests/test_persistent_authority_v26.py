import json, sqlite3
import pytest
import radar_persistent_authority_v1 as pa
from radar_investment_memory import init_memory as real_init_memory


def _db(monkeypatch,tmp_path):
    path=str(tmp_path/'authority.sqlite')
    def connect():
        c=sqlite3.connect(path);c.execute('create table if not exists control(key text primary key,value text)');c.commit();return c
    monkeypatch.setattr(pa,'con',connect);monkeypatch.setattr(pa,'init_db',lambda:None);monkeypatch.setattr(pa,'init_memory',real_init_memory)
    c=connect();real_init_memory(c);c.close();return path


def _row(origin='17',h='hash-a'):
    payload={'entry_price':100.0,'decision_state':'WAIT','immutable':True,'real_trading':False}
    return {'origin_node':'cloud-primary','origin_id':origin,'created_at':'2026-09-08T10:00:00+00:00',
      'target_date':'2026-09-09T10:00:00+00:00','symbol':'MSFT','horizon':'1d','model_version':'v1',
      'prediction_hash':h,'local_prediction_id':'pid-'+origin,'feature_fingerprint':'ff','thesis_fingerprint':'tf',
      'confidence':0.5,'uncertainty':{},'decision_state':'WAIT','paper_allocation':None,
      'data_cutoff':'2026-09-08T10:00:00+00:00','known_at_boundary':'2026-09-08T10:00:00+00:00',
      'provenance_snapshot':{'lookahead':False},'payload':payload,'outcome':None,'evaluated_at':None}


def test_forward_restore_is_exact_idempotent_and_not_backfill(monkeypatch,tmp_path):
    _db(monkeypatch,tmp_path);row=_row()
    one=pa.restore_forward_authority([row]);two=pa.restore_forward_authority([row])
    assert one['restored']==1 and one['backfill_used'] is False and one['reconstructed'] is False
    assert two['restored']==0 and two['already_present']==1
    c=pa.con();r=c.execute('select origin_node,origin_id,created_at,target_date,asset,prediction_hash,payload,outcome from prediction_ledger').fetchone();boundary=c.execute("select value from control where key='shadow_forward_started_at'").fetchone()[0];c.close()
    assert r[:6]==('cloud-primary','17',row['created_at'],row['target_date'],'MSFT','hash-a')
    assert json.loads(r[6])['entry_price']==100.0 and r[7] is None
    assert boundary==row['created_at']


def test_forward_restore_preserves_persisted_mature_outcome(monkeypatch,tmp_path):
    _db(monkeypatch,tmp_path);row=_row();row['outcome']={'return':0.02,'backfilled':False};row['evaluated_at']='2026-09-09T10:05:00+00:00'
    pa.restore_forward_authority([row]);c=pa.con();r=c.execute('select outcome,evaluated_at from prediction_ledger').fetchone();c.close()
    assert json.loads(r[0])['backfilled'] is False and r[1]==row['evaluated_at']


def test_forward_authority_conflict_fails_closed(monkeypatch,tmp_path):
    _db(monkeypatch,tmp_path);pa.restore_forward_authority([_row()])
    with pytest.raises(RuntimeError,match='authority conflict'):pa.restore_forward_authority([_row(h='different')])


def test_generic_restore_does_not_invent_columns(monkeypatch,tmp_path):
    _db(monkeypatch,tmp_path);c=pa.con();c.execute('create table sample(id integer primary key,ts text,payload text)');c.commit()
    n=pa._restore_generic(c,'sample',[{'payload':{'id':7,'ts':'observed','payload':{'x':1},'invented':'no'}}]);c.commit();r=c.execute('select id,ts,payload from sample').fetchone();c.close()
    assert n==1 and r[0]==7 and r[1]=='observed' and json.loads(r[2])=={'x':1}
    assert pa.REAL_TRADING is False
