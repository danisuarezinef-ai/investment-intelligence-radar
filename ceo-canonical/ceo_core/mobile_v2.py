from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
import json, os, time, hashlib, shutil

@dataclass(slots=True)
class MobileRuntimePolicy:
    max_temp_c: float = 43.0
    min_battery_pct: int = 25
    require_charging_for_heavy: bool = True
    heavy_ram_gb: float = 10.0
    max_model_storage_gb: float = 40.0
    night_start_hour: int = 1
    night_end_hour: int = 7

class MobileThermalBatteryGuard:
    def __init__(self, policy: MobileRuntimePolicy|None=None): self.policy=policy or MobileRuntimePolicy()
    def allow(self, *, temperature_c: float|None, battery_pct: int|None, charging: bool|None, estimated_ram_gb: float=0.0)->dict[str,Any]:
        blockers=[]
        if temperature_c is not None and temperature_c >= self.policy.max_temp_c: blockers.append('temperature')
        if battery_pct is not None and battery_pct < self.policy.min_battery_pct: blockers.append('battery')
        if estimated_ram_gb >= self.policy.heavy_ram_gb and self.policy.require_charging_for_heavy and charging is False: blockers.append('heavy_requires_charging')
        return {'allowed':not blockers,'blockers':blockers,'policy':asdict(self.policy)}

class MobileModelSelector:
    TIERS=[
        ('3B-q4',3.0,1),('7-8B-q4',6.0,2),('12-14B-q4',10.0,3),('20-24B-q4',16.0,4),('30-32B-q4',22.0,5)
    ]
    def choose(self, *, ram_available_gb: float, task_weight:int=2, temperature_c:float|None=None, battery_pct:int|None=None, charging:bool|None=None)->dict[str,Any]:
        guard=MobileThermalBatteryGuard()
        candidates=[]
        for label,ram,quality in self.TIERS:
            if ram <= max(0.0,ram_available_gb*0.82) and quality <= max(1,task_weight+1):
                g=guard.allow(temperature_c=temperature_c,battery_pct=battery_pct,charging=charging,estimated_ram_gb=ram)
                if g['allowed']: candidates.append((quality,label,ram))
        if not candidates:return {'selected':None,'reason':'no_safe_tier'}
        q,label,ram=max(candidates);return {'selected':label,'estimated_ram_gb':ram,'quality_tier':q,'reason':'highest_safe_fit'}

class MobileModelCache:
    def __init__(self, root:Path, quota_gb:float=40.0):
        self.root=(root/'models').resolve();self.root.mkdir(parents=True,exist_ok=True);self.meta=self.root/'cache.json';self.quota=int(quota_gb*1024**3)
    def _load(self):
        try:return json.loads(self.meta.read_text())
        except Exception:return {}
    def _save(self,d):self.meta.write_text(json.dumps(d,indent=2),encoding='utf-8')
    def register(self,path:Path)->dict[str,Any]:
        path=path.resolve();data=path.read_bytes();d=self._load();d[path.name]={'path':str(path),'size':len(data),'sha256':hashlib.sha256(data).hexdigest(),'last_used':time.time()};self._save(d);self.enforce();return d[path.name]
    def touch(self,name:str):
        d=self._load();
        if name in d:d[name]['last_used']=time.time();self._save(d)
    def enforce(self)->list[str]:
        d=self._load();removed=[]
        def total():return sum(int(v.get('size',0)) for v in d.values())
        for name,row in sorted(d.items(),key=lambda kv:kv[1].get('last_used',0)):
            if total()<=self.quota:break
            p=Path(row.get('path',''))
            try:p.unlink(missing_ok=True)
            except Exception:pass
            d.pop(name,None);removed.append(name)
        self._save(d);return removed

class MobileNightQueuePolicy:
    def __init__(self, policy:MobileRuntimePolicy|None=None):self.policy=policy or MobileRuntimePolicy()
    def eligible_now(self, *, hour:int|None=None, charging:bool, battery_pct:int, temperature_c:float|None=None)->dict[str,Any]:
        h=time.localtime().tm_hour if hour is None else hour
        in_window=self.policy.night_start_hour<=h<self.policy.night_end_hour
        guard=MobileThermalBatteryGuard(self.policy).allow(temperature_c=temperature_c,battery_pct=battery_pct,charging=charging,estimated_ram_gb=self.policy.heavy_ram_gb)
        return {'eligible':in_window and charging and guard['allowed'],'in_window':in_window,'charging':charging,'guard':guard}

class ZeroCostFederatedScheduler:
    """Prefer local/mobile zero-cost execution before billable APIs."""
    def choose(self, *, windows_only:bool=False, mobile_online:bool=False, mobile_capable:bool=False, local_pc_capable:bool=True, free_cloud_available:bool=False)->dict[str,Any]:
        if windows_only:return {'target':'windows','cost_class':'local','reason':'windows_only'}
        if mobile_online and mobile_capable:return {'target':'mobile','cost_class':'local','reason':'zero_cost_mobile_preferred'}
        if local_pc_capable:return {'target':'windows','cost_class':'local','reason':'zero_cost_pc_fallback'}
        if free_cloud_available:return {'target':'free_cloud','cost_class':'free_tier','reason':'local_unavailable'}
        return {'target':None,'cost_class':'blocked','reason':'no_zero_cost_provider'}

class MobileBenchmarkRegistry:
    def __init__(self,path:Path):self.path=path;path.parent.mkdir(parents=True,exist_ok=True)
    def append(self,row:dict[str,Any]):
        clean={k:v for k,v in row.items() if not any(x in k.lower() for x in ('secret','token','password','api_key'))}
        with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(clean,ensure_ascii=False)+'\n')
        return clean
    def best(self,task_type:str)->dict[str,Any]|None:
        rows=[]
        if self.path.exists():
            for line in self.path.read_text(encoding='utf-8').splitlines():
                try:
                    r=json.loads(line)
                    if r.get('task_type')==task_type and r.get('success'):rows.append(r)
                except Exception:pass
        if not rows:return None
        return max(rows,key=lambda r:(float(r.get('quality',0)),-float(r.get('seconds',1e9))))
