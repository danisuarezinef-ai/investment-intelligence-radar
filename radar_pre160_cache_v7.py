"""Small dependency-aware async cache used by Cloud v7 audit surfaces."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

REAL_TRADING=False

@dataclass
class CacheEntry:
    value: Any = None
    updated_at: float = 0.0
    dependency_token: str = ''
    refresh_running: bool = False
    last_compute_ms: float | None = None
    last_error: str | None = None

class AsyncSnapshotCache:
    def __init__(self, ttl_seconds=60.0, stale_seconds=300.0):
        self.ttl=float(ttl_seconds);self.stale=float(stale_seconds);self._entries={};self._lock=threading.RLock()

    def _entry(self,key):
        with self._lock:return self._entries.setdefault(str(key),CacheEntry())

    def peek(self,key):
        """Return the latest completed value without computing or waiting."""
        with self._lock:
            e=self._entries.get(str(key))
            return e.value if e is not None else None

    def ready(self,key):
        with self._lock:
            e=self._entries.get(str(key));return bool(e is not None and e.value is not None)

    def invalidate(self,key):
        with self._lock:
            e=self._entries.get(str(key))
            if e:e.updated_at=0.0;e.dependency_token=''

    def _compute(self,key,dependency_token,fn):
        e=self._entry(key);started=time.monotonic()
        try:
            value=fn();elapsed=(time.monotonic()-started)*1000.0
            if isinstance(value,dict):
                value=dict(value);value['cache_compute_ms']=round(elapsed,2);value['cache_dependency_token']=str(dependency_token);value['real_trading']=False
            with self._lock:
                e.value=value;e.updated_at=time.monotonic();e.dependency_token=str(dependency_token);e.last_compute_ms=elapsed;e.last_error=None
        except Exception as exc:
            with self._lock:e.last_error=str(exc)[:700]
        finally:
            with self._lock:e.refresh_running=False

    def get(self,key,dependency_token,fn:Callable[[],Any],*,allow_stale=True,refresh_async=True):
        now=time.monotonic();e=self._entry(key);token=str(dependency_token)
        with self._lock:
            age=now-e.updated_at if e.updated_at else float('inf');same=e.dependency_token==token
            if e.value is not None and same and age<=self.ttl:return e.value
            usable_stale=e.value is not None and same and age<=self.stale
            if usable_stale and allow_stale:
                if refresh_async and not e.refresh_running:
                    e.refresh_running=True;threading.Thread(target=self._compute,args=(key,token,fn),daemon=True,name=f'cache-refresh-{key}').start()
                return e.value
            if e.refresh_running and e.value is not None and allow_stale:return e.value
            e.refresh_running=True
        self._compute(key,token,fn)
        e=self._entry(key)
        if e.value is None:raise RuntimeError(e.last_error or f'cache compute failed for {key}')
        return e.value

    def prewarm(self,key,dependency_token,fn):
        e=self._entry(key)
        with self._lock:
            if e.refresh_running:return False
            e.refresh_running=True
        threading.Thread(target=self._compute,args=(key,str(dependency_token),fn),daemon=True,name=f'cache-prewarm-{key}').start();return True

    def telemetry(self):
        now=time.monotonic();out={}
        with self._lock:
            for k,e in self._entries.items():
                out[k]={'age_seconds':None if not e.updated_at else round(now-e.updated_at,3),'refresh_running':e.refresh_running,
                        'ready':e.value is not None,'last_compute_ms':e.last_compute_ms,'last_error':e.last_error,'dependency_token':e.dependency_token}
        return {'entries':out,'prewarm_enabled':True,'async_refresh':True,'stale_while_revalidate':True,
                'dependency_keys':True,'nonblocking_peek':True,'ttl_seconds':self.ttl,'stale_seconds':self.stale,'real_trading':False}
