import cloud_service_v14 as v14
import radar_learning_evidence_41_50_v1 as ev


def test_evidence_normalization_is_forward_only_and_paper(monkeypatch):
    monkeypatch.setattr(ev,'_post',lambda payload,timeout=35:{'ok':True,'real_trading':False,'stats':[{'horizon':'1d','n':1,'matured':1,'natural_matured':1}], 'rows':[{
        'id':1,'created_at':'2026-09-10T00:00:00+00:00','evaluated_at':'2026-09-11T00:00:00+00:00','symbol':'META','horizon':'1d','model_version':'2.0.0',
        'prediction_hash':'p','feature_fingerprint':'f','thesis_fingerprint':'t','confidence':0.7,'uncertainty':{},'decision_state':'BUY',
        'data_cutoff':'2026-09-10T00:00:00+00:00','known_at_boundary':'2026-09-10T00:00:00+00:00','provenance_snapshot':{},
        'outcome':{'net_return':0.01,'cost':0.001,'benchmark_return':0.005,'excess_return':0.005,'backfilled':False}}]})
    out=ev.normalized_rows()
    row=out['normalized_rows'][0]
    assert row['matured'] is True and row['natural'] is True
    assert row['quality_checks']['pit_valid'] is True
    assert row['quality_checks']['backfilled'] is False
    assert row['real_trading'] is False


def test_v14_blocks_all_41_50_when_durable_evidence_unavailable(monkeypatch):
    monkeypatch.setattr(v14.evidence4150,'normalized_rows',lambda limit=400:{'ok':False,'status':'FAIL_CLOSED','error':'timeout','real_trading':False})
    monkeypatch.setattr(v14.base13,'runtime_board_31_40',lambda:{'status':'PENDING','tasks':[],'real_trading':False})
    out=v14.runtime_board_41_50()
    assert out['status']=='BLOCKED_EVIDENCE'
    assert all(out['tasks'][str(n)]['state']=='BLOCKED_EVIDENCE' for n in range(41,51))
    assert out['automatic_promotion'] is False
    assert out['live_execution_allowed'] is False
    assert out['real_trading'] is False


def test_v14_exposes_only_41_50_and_never_live(monkeypatch):
    rows=[{'matured':True,'natural':True,'decision_state':'BUY','evaluated_at':'2026-09-11T00:00:00+00:00','real_trading':False}]
    monkeypatch.setattr(v14.evidence4150,'normalized_rows',lambda limit=400:{'ok':True,'status':'EVIDENCE_READY','normalized_rows':rows,'stats':[],'real_trading':False})
    monkeypatch.setattr(v14.base13,'runtime_board_31_40',lambda:{'status':'PENDING','tasks':[],'real_trading':False})
    fake_tasks={str(n):{'state':'PENDING_SAMPLE','evidence':{'real_trading':False}} for n in range(41,61)}
    monkeypatch.setattr(v14.learning4160,'build_priorities_41_60',lambda **kwargs:{'tasks':fake_tasks,'source_max_evaluated_at':'2026-09-11T00:00:00+00:00','real_trading':False})
    out=v14.runtime_board_41_50()
    assert set(out['tasks'])=={str(n) for n in range(41,51)}
    assert out['natural_matured_actions']==1
    assert out['automatic_promotion'] is False
    assert out['automatic_release'] is False
    assert out['setup_1_6_allowed'] is False
    assert out['live_execution_allowed'] is False
    assert out['real_trading'] is False
