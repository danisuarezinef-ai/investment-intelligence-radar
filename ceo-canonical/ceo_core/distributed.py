from __future__ import annotations
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import hashlib,hmac,json,time
from .models import ProjectState,Task,TaskStatus

@dataclass(slots=True)
class NodeCapacity:
    node_id:str;cpu:int;ram_gb:float;gpu_vram_gb:float=0.0;browser_slots:int=0;throughput:float=0.0;online:bool=True

class CapacityRegistry:
    def register(self,state:ProjectState,node:NodeCapacity)->None:state.metadata.setdefault('nodes',{})[node.node_id]=asdict(node)|{'seen':datetime.now(timezone.utc).isoformat()}
    def best_node(self,state:ProjectState,task:Task)->str|None:
        rows=[]
        for nid,n in state.metadata.get('nodes',{}).items():
            if not n.get('online',True):continue
            score=float(n.get('throughput',0))+.01*float(n.get('ram_gb',0))+.02*float(n.get('gpu_vram_gb',0))+.005*float(n.get('browser_slots',0))
            if 'browser' in task.required_capabilities and int(n.get('browser_slots',0))<=0:continue
            rows.append((score,nid))
        return max(rows)[1] if rows else None

class DistributedCoordinator:
    def assign(self,state:ProjectState,tasks:list[Task],registry:CapacityRegistry)->dict[str,list[str]]:
        out={}
        for t in tasks:
            nid=registry.best_node(state,t)
            if nid:out.setdefault(nid,[]).append(t.id);t.metadata['assigned_node']=nid
        return out
    def recover_node(self,state:ProjectState,node_id:str)->list[str]:
        if node_id in state.metadata.get('nodes',{}):state.metadata['nodes'][node_id]['online']=False
        recovered=[]
        for t in state.tasks.values():
            if t.metadata.get('assigned_node')==node_id and t.status in {TaskStatus.RUNNING,TaskStatus.READY,TaskStatus.RETRY}:
                t.status=TaskStatus.RETRY;t.metadata.pop('assigned_node',None);recovered.append(t.id)
        return recovered

class SecureNodeEnvelope:
    def __init__(self,key:bytes):
        if len(key)<16:raise ValueError('key too short')
        self.key=key
    def seal(self,payload:dict)->str:
        raw=json.dumps(payload,separators=(',',':'),sort_keys=True).encode();sig=hmac.new(self.key,raw,hashlib.sha256).hexdigest();return raw.decode()+'.'+sig
    def open(self,envelope:str)->dict|None:
        try:
            raw,sig=envelope.rsplit('.',1);exp=hmac.new(self.key,raw.encode(),hashlib.sha256).hexdigest()
            return json.loads(raw) if hmac.compare_digest(sig,exp) else None
        except Exception:return None


class NodeDiscovery:
    def heartbeat(self,state:ProjectState,node:NodeCapacity)->dict:
        CapacityRegistry().register(state,node)
        row=state.metadata['nodes'][node.node_id];row['last_heartbeat_unix']=time.time();return row
    def expire(self,state:ProjectState,ttl_seconds:float=30.0)->list[str]:
        now=time.time();expired=[]
        for nid,row in state.metadata.get('nodes',{}).items():
            last=float(row.get('last_heartbeat_unix',now))
            if now-last>ttl_seconds and row.get('online',True):row['online']=False;expired.append(nid)
        return expired

class DistributedLeaseManager:
    def lease(self,state:ProjectState,task_id:str,node_id:str,ttl_seconds:float=60.0)->dict:
        token=hashlib.sha256(f'{state.id}:{task_id}:{node_id}:{time.time_ns()}'.encode()).hexdigest()[:24]
        row={'task_id':task_id,'node_id':node_id,'token':token,'expires':time.time()+ttl_seconds,'completed':False}
        state.metadata.setdefault('distributed_leases',{})[task_id]=row
        if task_id in state.tasks:state.tasks[task_id].metadata['assigned_node']=node_id
        return row
    def valid(self,state:ProjectState,task_id:str,token:str)->bool:
        row=state.metadata.get('distributed_leases',{}).get(task_id);return bool(row and not row.get('completed') and row.get('token')==token and float(row.get('expires',0))>=time.time())
    def complete(self,state:ProjectState,task_id:str,token:str,result_hash:str)->bool:
        if not self.valid(state,task_id,token):return False
        row=state.metadata['distributed_leases'][task_id]
        existing=state.metadata.setdefault('distributed_results',{}).get(task_id)
        if existing:return existing.get('result_hash')==result_hash
        state.metadata['distributed_results'][task_id]={'result_hash':result_hash,'node_id':row['node_id']};row['completed']=True;return True
    def reclaim_expired(self,state:ProjectState)->list[str]:
        now=time.time();out=[]
        for tid,row in state.metadata.get('distributed_leases',{}).items():
            if not row.get('completed') and float(row.get('expires',0))<now:
                t=state.tasks.get(tid)
                if t and t.status!=TaskStatus.COMPLETE:t.status=TaskStatus.RETRY;t.metadata.pop('assigned_node',None);out.append(tid)
        return out

class EncryptedNodeEnvelope:
    """Authenticated encryption for inter-node payloads using AES-GCM.

    A project/node shared secret is hashed to a 256-bit key. Secret-like fields are
    stripped before encryption so browser/API credentials remain local to each node.
    """
    SECRET_KEYS={'password','passwd','token','api_key','apikey','secret','cookie','cookies','authorization','credential','credentials'}
    def __init__(self,key:bytes):
        if len(key)<16:raise ValueError('key too short')
        import hashlib
        self.key=hashlib.sha256(key).digest()
    def sanitize(self,value):
        if isinstance(value,dict):
            return {k:self.sanitize(v) for k,v in value.items() if str(k).lower() not in self.SECRET_KEYS and not any(x in str(k).lower() for x in ('password','api_key','secret','cookie','auth_token'))}
        if isinstance(value,list):return [self.sanitize(v) for v in value]
        return value
    def seal(self,payload:dict)->str:
        import os,base64,json
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        clean=self.sanitize(payload);raw=json.dumps(clean,separators=(',',':'),sort_keys=True).encode();nonce=os.urandom(12);cipher=AESGCM(self.key).encrypt(nonce,raw,None);return base64.urlsafe_b64encode(nonce+cipher).decode()
    def open(self,envelope:str)->dict|None:
        import base64,json
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            blob=base64.urlsafe_b64decode(envelope.encode());nonce,cipher=blob[:12],blob[12:];raw=AESGCM(self.key).decrypt(nonce,cipher,None);return json.loads(raw.decode())
        except Exception:return None
