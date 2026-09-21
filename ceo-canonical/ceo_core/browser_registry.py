from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BrowserServiceRegistry:
    """Persistent service/profile catalog. Never stores passwords or cookie values."""
    def __init__(self,path: str|Path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
    def _load(self):
        try:return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        except Exception:return {}
    def upsert(self,name:str,*,profile_dir:str,start_url:str,capabilities:list[str],status:str='unknown',last_check:str|None=None)->None:
        data=self._load();data[name]={'profile_dir':profile_dir,'start_url':start_url,'capabilities':capabilities,'status':status,'last_check':last_check};tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(self.path)
    def get(self,name:str)->dict[str,Any]|None:return self._load().get(name)
    def list(self)->dict[str,dict[str,Any]]:return self._load()
