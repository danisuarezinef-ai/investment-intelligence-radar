import time
from radar_pre160_cache_v7 import AsyncSnapshotCache

def test_cache_reuses_same_dependency_and_recomputes_new_dependency():
    c=AsyncSnapshotCache(ttl_seconds=60,stale_seconds=120);calls={'n':0}
    def fn():calls['n']+=1;return {'value':calls['n']}
    a=c.get('x','a',fn,refresh_async=False);b=c.get('x','a',fn,refresh_async=False)
    assert a['value']==b['value']==1 and calls['n']==1
    d=c.get('x','b',fn,refresh_async=False)
    assert d['value']==2 and calls['n']==2
    t=c.telemetry();assert t['prewarm_enabled'] and t['async_refresh'] and t['stale_while_revalidate'] and t['dependency_keys']
    assert t['real_trading'] is False

def test_stale_value_can_be_served_while_refresh_runs():
    c=AsyncSnapshotCache(ttl_seconds=.001,stale_seconds=5);calls={'n':0}
    def fast():calls['n']+=1;return {'value':calls['n']}
    first=c.get('x','same',fast,refresh_async=False);time.sleep(.01)
    second=c.get('x','same',fast,allow_stale=True,refresh_async=True)
    assert first['value']==1 and second['value']==1
