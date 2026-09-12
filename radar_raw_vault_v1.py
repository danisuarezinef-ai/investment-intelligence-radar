"""Append-only content-addressed raw evidence vault.

Local files are an implementation primitive only. Production durability must still be
proved by deployment/storage evidence before release readiness can pass.
"""
from __future__ import annotations
import hashlib,json,os,tempfile
from pathlib import Path

REAL_TRADING=False

def canonical_bytes(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=str).encode('utf-8')
def digest(value):return hashlib.sha256(canonical_bytes(value)).hexdigest()
class RawVault:
    def __init__(self,root=None):
        base=root or os.getenv('RADAR_RAW_VAULT_DIR') or '.radar-data/raw-vault-v1';self.root=Path(base);self.root.mkdir(parents=True,exist_ok=True)
    def put(self,value,metadata=None):
        h=digest(value);path=self.root/f'{h}.json';envelope={'sha256':h,'payload':value,'metadata':metadata or {},'real_trading':False}
        if path.exists():
            existing=json.loads(path.read_text(encoding='utf-8'))
            if existing.get('sha256')!=h or digest(existing.get('payload'))!=h:raise RuntimeError('raw vault hash collision/corruption')
            return {'sha256':h,'path':str(path),'created':False,'real_trading':False}
        fd,tmp=tempfile.mkstemp(prefix=h+'.',suffix='.tmp',dir=self.root)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(envelope,f,sort_keys=True,separators=(',',':'),ensure_ascii=False)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return {'sha256':h,'path':str(path),'created':True,'real_trading':False}
    def get(self,h):
        path=self.root/f'{h}.json';obj=json.loads(path.read_text(encoding='utf-8'))
        if obj.get('sha256')!=h or digest(obj.get('payload'))!=h:raise RuntimeError('raw vault integrity failure')
        return obj
    def contract(self):return {'append_only':True,'content_addressed':'SHA-256','overwrite_allowed':False,'production_durability_verified':False,'real_trading':False}
