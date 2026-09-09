import sqlite3

import cloud_service_v3 as cloud


def test_learning_startup_retries_duplicate_column_race(monkeypatch):
    calls=[]
    def fake():
        calls.append(1)
        if len(calls)==1:
            raise sqlite3.OperationalError('duplicate column name: updated_at')
        return 'ok'
    monkeypatch.setattr(cloud.base_v2.base,'learning_loop',fake)
    monkeypatch.setattr(cloud.time,'sleep',lambda _seconds:None)
    assert cloud._resilient_learning_loop()== 'ok'
    assert len(calls)==2


def test_learning_startup_does_not_hide_unrelated_sqlite_errors(monkeypatch):
    def fake():
        raise sqlite3.OperationalError('database disk image is malformed')
    monkeypatch.setattr(cloud.base_v2.base,'learning_loop',fake)
    try:
        cloud._resilient_learning_loop()
    except sqlite3.OperationalError as exc:
        assert 'malformed' in str(exc)
    else:
        raise AssertionError('unrelated sqlite error must propagate')
