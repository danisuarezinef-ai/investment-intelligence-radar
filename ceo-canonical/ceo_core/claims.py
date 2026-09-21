from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit
import re
from typing import Any, Iterable

from .models import ProjectState, Task


class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    SUPPORTED = "supported"
    UNCERTAIN = "uncertain"
    CONFLICTED = "conflicted"
    REJECTED = "rejected"


@dataclass(slots=True)
class SourceRecord:
    id: str
    title: str = ""
    url: str = ""
    doi: str = ""
    content_hash: str = ""
    domain: str = ""
    quality: float = 0.5
    independent_group: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ClaimRecord:
    id: str
    text: str
    status: ClaimStatus = ClaimStatus.UNCERTAIN
    confidence: float = 0.5
    source_ids: list[str] | None = None
    task_ids: list[str] | None = None
    contradicts: list[str] | None = None
    metadata: dict[str, Any] | None = None


def _norm_text(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())


def _norm_doi(doi: str) -> str:
    doi = doi.strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi


def _norm_url(url: str) -> str:
    try:
        s = urlsplit(url.strip())
        host = s.netloc.lower().removeprefix("www.")
        path = s.path.rstrip("/")
        return urlunsplit((s.scheme.lower() or "https", host, path, "", ""))
    except Exception:
        return url.strip().lower()


class SourceRegistry:
    """Project-wide source identity and independence registry."""

    def _store(self, state: ProjectState) -> dict[str, dict[str, Any]]:
        return state.metadata.setdefault("sources", {})

    def identity_key(self, *, title: str = "", url: str = "", doi: str = "", content: str = "") -> str:
        if doi:
            return "doi:" + _norm_doi(doi)
        if url:
            return "url:" + _norm_url(url)
        if content:
            return "hash:" + sha256(content.encode("utf-8", errors="ignore")).hexdigest()
        return "title:" + _norm_text(title)

    def register(self, state: ProjectState, *, title: str = "", url: str = "", doi: str = "", content: str = "", quality: float = 0.5, metadata: dict[str, Any] | None = None) -> str:
        key = self.identity_key(title=title, url=url, doi=doi, content=content)
        sid = sha256(key.encode()).hexdigest()[:20]
        host = urlsplit(url).netloc.lower().removeprefix("www.") if url else ""
        group = (metadata or {}).get("independent_group") or (_norm_doi(doi).split("/")[0] if doi else host or sid)
        row = SourceRecord(id=sid, title=title, url=_norm_url(url) if url else "", doi=_norm_doi(doi), content_hash=(sha256(content.encode()).hexdigest() if content else ""), domain=host, quality=max(0.0,min(1.0,quality)), independent_group=str(group), metadata=metadata or {})
        current = self._store(state).get(sid)
        if current:
            # Preserve strongest known quality and enrich missing fields.
            merged = dict(current)
            for k,v in asdict(row).items():
                if v not in ("", None, [], {}): merged[k] = v
            merged["quality"] = max(float(current.get("quality", 0.5)), row.quality)
            self._store(state)[sid] = merged
        else:
            self._store(state)[sid] = asdict(row)
        return sid

    def independent_count(self, state: ProjectState, source_ids: Iterable[str]) -> int:
        store = self._store(state)
        groups = {store[s].get("independent_group") or s for s in source_ids if s in store}
        return len(groups)

    def average_quality(self, state: ProjectState, source_ids: Iterable[str]) -> float:
        rows = [self._store(state).get(s) for s in source_ids]
        vals = [float(r.get("quality", 0.5)) for r in rows if r]
        return sum(vals)/len(vals) if vals else 0.5

    def record_domain_outcome(self,state:ProjectState,source_id:str,reliable:bool)->None:
        row=self._store(state).get(source_id)
        if not row:return
        domain=str(row.get("domain") or row.get("independent_group") or source_id)
        rep=state.metadata.setdefault("source_reputation",{}).setdefault(domain,{"success":0,"failure":0})
        rep["success" if reliable else "failure"]+=1
        total=rep["success"]+rep["failure"]
        row["historical_reputation"]=round((rep["success"]+1)/(total+2),4)

    def domain_reputation(self,state:ProjectState,domain:str)->float:
        rep=state.metadata.get("source_reputation",{}).get(domain)
        if not rep:return .5
        return (float(rep.get("success",0))+1)/(float(rep.get("success",0))+float(rep.get("failure",0))+2)

    def circular_groups(self, state: ProjectState, source_ids: Iterable[str]) -> list[list[str]]:
        store = self._store(state); by_group: dict[str,list[str]]={}
        for sid in source_ids:
            row=store.get(sid)
            if row: by_group.setdefault(str(row.get("independent_group") or sid),[]).append(sid)
        return [ids for ids in by_group.values() if len(ids)>1]


class ClaimRegistry:
    """Central auditable registry of important project claims."""
    NEGATIONS=(" no "," not "," does not "," false "," invalid "," unsupported ")

    def _store(self,state:ProjectState)->dict[str,dict[str,Any]]:
        return state.metadata.setdefault("claims",{})

    def register(self,state:ProjectState,text:str,*,task_id:str|None=None,source_ids:list[str]|None=None,status:ClaimStatus=ClaimStatus.UNCERTAIN,confidence:float=0.5,metadata:dict[str,Any]|None=None)->str:
        norm=_norm_text(text); cid=sha256(norm.encode()).hexdigest()[:20]
        store=self._store(state); row=store.get(cid)
        if not row:
            rec=ClaimRecord(cid,text,status,max(0,min(1,confidence)),list(source_ids or []),[task_id] if task_id else [],[],metadata or {})
            store[cid]=asdict(rec); store[cid]["status"]=status.value
        else:
            if task_id and task_id not in row.setdefault("task_ids",[]): row["task_ids"].append(task_id)
            for sid in source_ids or []:
                if sid not in row.setdefault("source_ids",[]): row["source_ids"].append(sid)
            row["confidence"]=max(float(row.get("confidence",0.5)),confidence)
            if status in {ClaimStatus.VERIFIED,ClaimStatus.REJECTED,ClaimStatus.CONFLICTED}: row["status"]=status.value
        self._detect_conflicts(state,cid)
        return cid

    def _opposite(self,a:str,b:str)->bool:
        na,nb=" "+_norm_text(a)+" "," "+_norm_text(b)+" "
        # Same backbone with one containing negation is a conservative conflict heuristic.
        neg_a=any(x in na for x in self.NEGATIONS); neg_b=any(x in nb for x in self.NEGATIONS)
        if neg_a==neg_b:return False
        def strip_neg(x:str)->set[str]:
            return {w for w in x.split() if w not in {"no","not","does","false","invalid","unsupported"}}
        sa,sb=strip_neg(na),strip_neg(nb)
        return bool(sa and sb and len(sa&sb)/max(1,len(sa|sb))>=0.55)

    def _detect_conflicts(self,state:ProjectState,cid:str)->None:
        store=self._store(state); row=store[cid]
        for oid,other in list(store.items()):
            if oid==cid:continue
            if self._opposite(str(row.get("text","")),str(other.get("text",""))):
                if oid not in row.setdefault("contradicts",[]): row["contradicts"].append(oid)
                if cid not in other.setdefault("contradicts",[]): other["contradicts"].append(cid)
                row["status"]=ClaimStatus.CONFLICTED.value;other["status"]=ClaimStatus.CONFLICTED.value

    def unresolved(self,state:ProjectState)->list[dict[str,Any]]:
        return [v for v in self._store(state).values() if v.get("status") in {ClaimStatus.UNCERTAIN.value,ClaimStatus.CONFLICTED.value}]

    def update_status(self,state:ProjectState,claim_id:str,status:ClaimStatus,confidence:float|None=None)->None:
        row=self._store(state).get(claim_id)
        if not row:return
        row["status"]=status.value
        if confidence is not None:row["confidence"]=max(0,min(1,confidence))


class ClaimExtractor:
    """Protocol-first claim ingestion. Workers can return structured claims in metadata."""
    def ingest_task(self,state:ProjectState,task:Task,claims:ClaimRegistry,sources:SourceRegistry)->list[str]:
        source_ids=[]
        for src in task.metadata.get("sources",[]):
            if isinstance(src,str): source_ids.append(sources.register(state,url=src))
            elif isinstance(src,dict): source_ids.append(sources.register(state,**{k:src.get(k,"") for k in ("title","url","doi","content")},quality=float(src.get("quality",0.5)),metadata=src.get("metadata") or {}))
        ids=[]
        structured=task.metadata.get("claims",[])
        for row in structured:
            if isinstance(row,str): text=row; conf=float(task.confidence or .5); status=ClaimStatus.SUPPORTED
            else:
                text=str(row.get("text",""));conf=float(row.get("confidence",task.confidence or .5));status=ClaimStatus(str(row.get("status","supported")))
            if text.strip(): ids.append(claims.register(state,text,task_id=task.id,source_ids=source_ids,status=status,confidence=conf))
        return ids
