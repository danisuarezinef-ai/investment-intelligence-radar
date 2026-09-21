from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class BrowserLifecycleDecision:
    recycle: bool
    suspend: bool
    reason: str


class BrowserPressureDetector:
    """Detects when more browser workers are degrading throughput or memory efficiency."""
    def assess(self,*,workers:int,throughput:float,previous_workers:int|None=None,previous_throughput:float|None=None,ram_mb_per_worker:float=220,ram_limit_mb:float|None=None)->BrowserLifecycleDecision:
        if ram_limit_mb and workers*ram_mb_per_worker>ram_limit_mb:
            return BrowserLifecycleDecision(True,True,"browser_ram_pressure")
        if previous_workers and previous_throughput is not None and workers>previous_workers and throughput<=previous_throughput*1.03:
            return BrowserLifecycleDecision(True,False,"browser_concurrency_saturated")
        return BrowserLifecycleDecision(False,False,"healthy")


class BrowserLifecyclePolicy:
    """CEO closes/suspends idle contexts and rehydrates sessions from persistent profiles/URLs."""
    def should_recycle(self,*,rss_mb:float,requests:int,max_rss_mb:float=900,max_requests:int=50)->bool:
        return rss_mb>=max_rss_mb or requests>=max_requests
    def suspend_descriptor(self,conversation_id:str,url:str,profile_dir:str)->dict:
        return {"conversation_id":conversation_id,"url":url,"profile_dir":profile_dir,"suspended":True}
