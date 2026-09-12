import time

import cloud_service_v7 as v7
from radar_pre160_cache_v7 import AsyncSnapshotCache


def test_cold_http_snapshot_returns_fail_closed_without_calling_expensive_source(monkeypatch):
    monkeypatch.setattr(v7,'_CACHE',AsyncSnapshotCache(ttl_seconds=60,stale_seconds=300))
    monkeypatch.setattr(v7,'_source_inputs',lambda: (_ for _ in ()).throw(AssertionError('HTTP cold path must not read v6 evidence')))
    started=time.monotonic();out=v7.tasks_201_270_cached();elapsed=time.monotonic()-started
    assert elapsed < 0.25
    assert out['status']=='WARMING_FAIL_CLOSED'
    assert out['source_ready'] is False
    assert set(out['tasks'])=={str(i) for i in range(201,271)}
    assert all(x['state']=='NOT_VERIFIED' for x in out['tasks'].values())
    assert out['setup_allowed'] is False and out['automatic_release'] is False and out['real_trading'] is False


def test_completed_background_snapshot_is_returned_by_nonblocking_peek(monkeypatch):
    cache=AsyncSnapshotCache(ttl_seconds=60,stale_seconds=300);monkeypatch.setattr(v7,'_CACHE',cache)
    cache.get('201-270','token',lambda:{'status':'PRE160_TASKS_201_270','source_ready':True,'tasks':{},'real_trading':False},refresh_async=False)
    monkeypatch.setattr(v7,'_source_inputs',lambda: (_ for _ in ()).throw(AssertionError('HTTP hot path must not read v6 evidence')))
    out=v7.tasks_201_270_cached()
    assert out['status']=='PRE160_TASKS_201_270'
    assert out['source_ready'] is True
    assert out['real_trading'] is False


def test_warming_master_gate_is_manual_and_blocks_every_execution_authority(monkeypatch):
    monkeypatch.setattr(v7,'_CACHE',AsyncSnapshotCache())
    m=v7.tasks_201_270_cached()['master_gate']
    assert m['status']=='BLOCKED_PRE160'
    assert m['manual_review_only'] is True
    assert m['setup_allowed'] is False
    assert m['automatic_release'] is False
    assert m['live_execution_allowed'] is False
    assert m['can_trade'] is False and m['real_trading'] is False
