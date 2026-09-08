import json,sqlite3
import pytest
import radar_core
import radar_forward_engine as engine
from radar_investment_memory import init_memory,freeze_prediction,evaluate_prediction,append_thesis_event

def test_forward_ledger_rejects_backdating_and_lookahead():
 db=sqlite3.connect(':memory:');clock=lambda:'2026-06-01T12:00:00+00:00'
 with pytest.raises(ValueError):freeze_prediction(db,{'created_at':'2026-05-31T12:00:00+00:00','symbol':'X','horizon':'1d','model_version':'v','provenance_snapshot':{'lookahead':False}},clock=clock)
 with pytest.raises(ValueError):freeze_prediction(db,{'symbol':'X','horizon':'1d','model_version':'v','provenance_snapshot':{}},clock=clock)

def test_prediction_core_and_outcome_are_single_assignment():
 db=sqlite3.connect(':memory:');clock=lambda:'2026-06-01T12:00:00+00:00'
 pid=freeze_prediction(db,{'symbol':'X','horizon':'1d','model_version':'v','provenance_snapshot':{'lookahead':False}},clock=clock)
 with pytest.raises(sqlite3.IntegrityError):db.execute("update prediction_ledger set confidence=.9 where id=?",(pid,))
 with pytest.raises(ValueError):evaluate_prediction(db,pid,{'return':1},'2026-06-01T13:00:00+00:00')
 evaluate_prediction(db,pid,{'return':1},'2026-06-02T12:00:00+00:00')
 with pytest.raises(ValueError):evaluate_prediction(db,pid,{'return':2},'2026-06-03T12:00:00+00:00')

def test_thesis_lifecycle_is_append_only():
 db=sqlite3.connect(':memory:');append_thesis_event(db,'t','NEW',{});append_thesis_event(db,'t','ACTIVE',{})
 with pytest.raises(ValueError):append_thesis_event(db,'t','NEW',{})
 with pytest.raises(sqlite3.IntegrityError):db.execute("update thesis_events set state='CLOSED'")
 with pytest.raises(sqlite3.IntegrityError):db.execute('delete from thesis_events')

def test_engine_requires_every_external_gate(tmp_path,monkeypatch):
 monkeypatch.setattr(radar_core,'DB',str(tmp_path/'r.db'));radar_core.init_db();monkeypatch.setattr(engine,'enabled',lambda:True)
 assert not engine.start_forward_ledger({'local_tests':True})['started']
 gates={k:True for k in ('local_tests','github_ci','windows_build','installer','migration','sync_idempotent')}
 first=engine.start_forward_ledger(gates);second=engine.start_forward_ledger(gates)
 assert first['started'] and first['started_at']==second['started_at'] and first['real_trading'] is False

def test_engine_does_not_capture_pre_start_rows(tmp_path,monkeypatch):
 monkeypatch.setattr(radar_core,'DB',str(tmp_path/'r.db'));radar_core.init_db()
 from radar_learning import init_learning_db
 init_learning_db();c=radar_core.con();c.execute("insert into control(key,value) values(?,?)",(engine.CONTROL_KEY,'2026-06-01T12:00:00+00:00'))
 c.execute("insert into predictions(created_at,symbol,horizon,model_version,score,confidence,entry_price,thesis,features,regime,source_snapshot) values(?,?,?,?,?,?,?,?,?,?,?)",('2026-05-31T12:00:00+00:00','X','1d','v',1,.5,10,'t','{}','mixed','{}'));c.commit();c.close()
 assert engine.capture_forward_predictions()['captured']==0

def test_live_holdout_cannot_auto_replace_active_model(tmp_path,monkeypatch):
 monkeypatch.setattr(radar_core,'DB',str(tmp_path/'r.db'))
 import radar_learning as rl,radar_learning_guarded as guarded
 guarded.init_guarded_learning_db();model=rl.active_model()
 rows=[{'ts':f'2026-01-{i+1:02d}','features':{},'return_pct':1,'stored_confidence':.5,'stored_hit':1} for i in range(40)]
 monkeypatch.setattr(guarded,'_rows',lambda:rows)
 monkeypatch.setattr(guarded,'_candidate_weights',lambda current,train:(dict(current),{k:0 for k in current}))
 calls={'n':0}
 def metrics(weights,sample):
  calls['n']+=1
  return {'n':len(sample),'hit_rate':.8,'brier':.1,'signed_return':1,'objective':.5 if calls['n']%2 else .7}
 monkeypatch.setattr(guarded,'evaluate_weights',metrics)
 result=guarded.guarded_learn(40)
 assert result['accepted'] is False and result['shadow_qualified'] is True
 assert rl.active_model()['version']==model['version']

def test_decision_sync_uses_origin_identity_and_is_incremental(tmp_path,monkeypatch):
 monkeypatch.setattr(radar_core,'DB',str(tmp_path/'r.db'));radar_core.init_db()
 import radar_learning_sync as sync
 monkeypatch.setattr(sync,'SYNC_URL','mock://sync');monkeypatch.setattr(sync,'SYNC_TOKEN','test')
 sent=[];monkeypatch.setattr(sync,'_post',lambda payload:sent.append(payload) or {'ok':True})
 db=radar_core.con();freeze_prediction(db,{'symbol':'X','horizon':'1d','model_version':'v','provenance_snapshot':{'lookahead':False}});append_thesis_event(db,'t','NEW',{});db.close()
 first=sync.sync_learning_once();second=sync.sync_learning_once()
 assert first['decision_forward_ledger']==1 and second['decision_forward_ledger']==0
 assert first['decision_thesis_events']==1 and second['decision_thesis_events']==0
 row=sent[0]['decision_forward_ledger'][0]
 assert row['origin_node']==sync.NODE_ID and row['origin_id']=='1' and 'id' not in row
