import json
import radar_core
import radar_shadow_experiment_v2 as se
from radar_investment_memory import init_memory


def _tmp(tmp_path,monkeypatch):
    monkeypatch.setattr(radar_core,'DB',str(tmp_path/'radar.db'))
    monkeypatch.setattr(radar_core,'STATUS',str(tmp_path/'status.json'))
    monkeypatch.setattr(radar_core,'LOG',str(tmp_path/'worker.log'))
    monkeypatch.setattr(radar_core,'PID',str(tmp_path/'worker.pid'))
    radar_core.init_db();c=radar_core.con();init_memory(c);c.execute("insert or replace into control(key,value) values(?,?)",(se.CONTROL_KEY,'2026-01-01T00:00:00+00:00'));c.commit();c.close()


def _insert(pred_id,created='2026-01-02T00:00:00+00:00',outcome=None,evaluated=None,lookahead=False,immutable=True):
    c=radar_core.con();payload={'immutable':immutable,'real_trading':False};prov={'lookahead':lookahead}
    c.execute('''insert into prediction_ledger(id,origin_node,origin_id,created_at,target_date,asset,horizon,model_version,prediction_hash,feature_fingerprint,thesis_fingerprint,confidence,uncertainty,decision_state,paper_allocation,data_cutoff,known_at_boundary,provenance_snapshot,payload,outcome,evaluated_at)
                 values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (pred_id,'test',pred_id,created,'2026-01-03T00:00:00+00:00','MSFT','1d','v1',pred_id+'h',pred_id+'f',pred_id+'t',.8,'{}','WAIT',None,created,created,json.dumps(prov),json.dumps(payload),json.dumps(outcome) if outcome is not None else None,evaluated))
    c.commit();c.close()


def test_shadow_evidence_is_fail_closed_without_benchmark_and_costs(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_insert('p1',outcome={'return':.02},evaluated='2026-01-03T01:00:00+00:00')
    out=se.shadow_experiment_evidence()
    assert out['matured_predictions']==1
    assert out['ledger_integrity'] is True
    assert out['pit_verified'] is True
    assert out['excess_return_pct'] is None
    assert out['benchmark_evidence_available'] is False
    assert out['costs_included'] is False
    assert out['real_trading'] is False


def test_shadow_evidence_detects_backfill(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_insert('p1',created='2025-12-31T00:00:00+00:00',outcome={'return':.02},evaluated='2026-01-03T01:00:00+00:00')
    out=se.shadow_experiment_evidence()
    assert out['ledger_integrity'] is False
    assert out['integrity_errors'][0]['no_backfill'] is False


def test_shadow_evidence_detects_lookahead(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch);_insert('p1',outcome={'return':.02},evaluated='2026-01-03T01:00:00+00:00',lookahead=True)
    out=se.shadow_experiment_evidence()
    assert out['ledger_integrity'] is False
    assert out['integrity_errors'][0]['lookahead_false'] is False


def test_shadow_drawdown_uses_real_matured_sequence(tmp_path,monkeypatch):
    _tmp(tmp_path,monkeypatch)
    _insert('p1',created='2026-01-02T00:00:00+00:00',outcome={'return_pct':10},evaluated='2026-01-03T01:00:00+00:00')
    _insert('p2',created='2026-01-04T00:00:00+00:00',outcome={'return_pct':-10},evaluated='2026-01-05T01:00:00+00:00')
    out=se.shadow_experiment_evidence()
    assert out['matured_predictions']==2
    assert out['max_drawdown_pct']<0
