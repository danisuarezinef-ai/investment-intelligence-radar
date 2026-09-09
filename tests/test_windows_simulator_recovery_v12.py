from pathlib import Path
import radar_simulation_v2 as sim


def test_updater_installs_simulation_lab_binary():
    text=Path('radar_updater_v2.py').read_text(encoding='utf-8')
    assert "'RadarSimulationLab.exe'" in text
    assert 'PAYLOAD_BINARIES' in text
    assert 'for name in PAYLOAD_BINARIES' in text


def test_stable_version_bumped_for_simulator_recovery():
    import json
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int,version.split('.'))) >= (1,5,8)


def test_replay_attempts_history_recovery_once(monkeypatch):
    calls={'series':0,'history':0}
    fake_days=[(f'2026-01-0{i}',{'MSFT':100.0+i}) for i in range(1,6)]
    def series(*args,**kwargs):
        calls['series']+=1
        return [] if calls['series']==1 else fake_days
    monkeypatch.setattr(sim,'init_simulation_db',lambda:None)
    monkeypatch.setattr(sim,'_series_by_day',series)
    monkeypatch.setattr(sim,'collect_history',lambda: calls.__setitem__('history',calls['history']+1))
    class Stop(Exception): pass
    monkeypatch.setattr(sim,'con',lambda: (_ for _ in ()).throw(Stop()))
    try:
        sim.replay_historical(run_id='test-recovery')
    except Stop:
        pass
    assert calls['history']==1
    assert calls['series']==2


def test_replay_fails_clearly_after_unsuccessful_recovery(monkeypatch):
    monkeypatch.setattr(sim,'init_simulation_db',lambda:None)
    monkeypatch.setattr(sim,'_series_by_day',lambda *a,**k: [])
    calls={'n':0}
    monkeypatch.setattr(sim,'collect_history',lambda: calls.__setitem__('n',calls['n']+1))
    try:
        sim.replay_historical(run_id='test-no-history')
    except ValueError as exc:
        assert 'after automatic history recovery' in str(exc)
    else:
        raise AssertionError('replay should fail closed without sufficient history')
    assert calls['n']==1
