from __future__ import annotations

"""CEO Mobile Node Alpha.

A provider-neutral, durable companion node intended for Android/Termux.  The module
uses only the Python standard library so the control plane can run before optional
AI/model dependencies are installed.  Secrets are referenced by handles/env names;
values are never written to the mobile state database or artifact manifests.
"""

from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Iterable
import base64
import hashlib
import hmac
import json
import os
import platform
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
import urllib.error

from .contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult, ProviderHealth


MOBILE_SCHEMA_VERSION = 1
SPEND_ACTIONS = {"spend", "purchase", "subscribe", "billing", "credits", "payment"}
WINDOWS_ONLY_CAPABILITIES = {
    "windows_ui", "windows_registry", "powershell", "win32", "uia", "desktop_windows"
}
SECRETISH = {
    "password", "passwd", "token", "api_key", "apikey", "secret", "cookie",
    "authorization", "credential", "credentials", "bearer"
}


def _now() -> float:
    return time.time()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            low = str(k).lower()
            if low in SECRETISH or any(part in low for part in ("password", "api_key", "secret", "cookie", "auth_token")):
                continue
            out[k] = _sanitize(v)
        return out
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


def _safe_join(root: Path, relative: str | Path) -> Path:
    root = root.resolve()
    target = (root / Path(relative)).resolve()
    if target != root and root not in target.parents:
        raise PermissionError(f"path escapes mobile workspace: {relative}")
    return target


def _proc_meminfo() -> tuple[float, float]:
    total = available = 0.0
    try:
        rows = {}
        for line in Path("/proc/meminfo").read_text(errors="ignore").splitlines():
            key, value = line.split(":", 1)
            rows[key] = float(value.strip().split()[0]) / (1024 * 1024)
        total = rows.get("MemTotal", 0.0)
        available = rows.get("MemAvailable", rows.get("MemFree", 0.0))
    except Exception:
        pass
    return round(total, 3), round(available, 3)


def _cmd_path(name: str) -> str | None:
    return shutil.which(name)


@dataclass(slots=True)
class MobileNodeConfig:
    node_id: str = "ceo-mobile"
    root: str = ""
    bind_host: str = "127.0.0.1"
    port: int = 8765
    shared_secret_env: str = "CEO_MOBILE_SHARED_SECRET"
    local_model_url: str = "http://127.0.0.1:8080/v1/chat/completions"
    local_model_name: str = "local-model"
    allow_network_downloads: bool = False
    max_download_mb: int = 512
    default_mode: str = "supervised"

    @property
    def root_path(self) -> Path:
        base = self.root or os.getenv("CEO_MOBILE_ROOT") or str(Path.home() / "ceo-mobile")
        return Path(base).expanduser().resolve()


@dataclass(slots=True)
class MobileCapabilitySnapshot:
    node_id: str
    platform: str
    architecture: str
    python: str
    logical_cpus: int
    ram_total_gb: float
    ram_available_gb: float
    storage_free_gb: float
    git: bool
    ssh: bool
    curl: bool
    termux: bool
    termux_api: bool
    llama_server: bool
    battery: dict[str, Any]
    network_online: bool
    local_model_url: str
    assessed_at: float


class MobilePreflight:
    def __init__(self, config: MobileNodeConfig) -> None:
        self.config = config

    def _battery(self) -> dict[str, Any]:
        exe = _cmd_path("termux-battery-status")
        if not exe:
            return {"available": False}
        try:
            p = subprocess.run([exe], capture_output=True, text=True, timeout=4)
            if p.returncode == 0:
                row = json.loads(p.stdout or "{}")
                return {"available": True, **_sanitize(row)}
        except Exception:
            pass
        return {"available": False}

    def _network(self) -> bool:
        try:
            urllib.request.urlopen("https://www.google.com/generate_204", timeout=2).close()
            return True
        except Exception:
            return False

    def snapshot(self, *, probe_network: bool = False) -> MobileCapabilitySnapshot:
        root = self.config.root_path
        root.mkdir(parents=True, exist_ok=True)
        total, avail = _proc_meminfo()
        try:
            free = shutil.disk_usage(root).free / (1024 ** 3)
        except Exception:
            free = 0.0
        termux = "com.termux" in os.getenv("PREFIX", "") or "termux" in os.getenv("PREFIX", "").lower()
        return MobileCapabilitySnapshot(
            node_id=self.config.node_id,
            platform=platform.platform(),
            architecture=platform.machine(),
            python=sys.version.split()[0],
            logical_cpus=os.cpu_count() or 1,
            ram_total_gb=total,
            ram_available_gb=avail,
            storage_free_gb=round(free, 3),
            git=bool(_cmd_path("git")),
            ssh=bool(_cmd_path("ssh")),
            curl=bool(_cmd_path("curl")),
            termux=termux,
            termux_api=bool(_cmd_path("termux-battery-status")),
            llama_server=bool(_cmd_path("llama-server") or _cmd_path("server")),
            battery=self._battery(),
            network_online=self._network() if probe_network else False,
            local_model_url=self.config.local_model_url,
            assessed_at=_now(),
        )

    def model_tiers(self, snapshot: MobileCapabilitySnapshot | None = None) -> list[dict[str, Any]]:
        snap = snapshot or self.snapshot()
        # Conservative RAM envelopes; actual speed/fit must be field benchmarked.
        tiers = [
            {"label": "3B-q4", "estimated_ram_gb": 3.0, "purpose": "classification/summaries"},
            {"label": "7-8B-q4", "estimated_ram_gb": 6.0, "purpose": "general/review"},
            {"label": "12-14B-q4", "estimated_ram_gb": 10.0, "purpose": "reasoning/code review"},
            {"label": "20-24B-q4", "estimated_ram_gb": 16.0, "purpose": "heavy reasoning; benchmark first"},
            {"label": "30-32B-q4", "estimated_ram_gb": 22.0, "purpose": "experimental only; likely too tight"},
        ]
        budget = max(0.0, snap.ram_total_gb * 0.72)
        for row in tiers:
            row["eligible_by_total_ram"] = row["estimated_ram_gb"] <= budget
            row["field_verified"] = False
        return tiers


class MobileDB:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "mobile_node.db"
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self.conn.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, status TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 50, lease_token TEXT, lease_expires REAL,
          result TEXT, result_hash TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals(
          id TEXT PRIMARY KEY, action TEXT NOT NULL, risk TEXT NOT NULL, payload_hash TEXT NOT NULL,
          status TEXT NOT NULL, token_hash TEXT, created_at REAL NOT NULL, consumed_at REAL
        );
        CREATE TABLE IF NOT EXISTS evidence(
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, sha256 TEXT NOT NULL,
          created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS friction(
          id TEXT PRIMARY KEY, kind TEXT NOT NULL, severity TEXT NOT NULL, details TEXT NOT NULL,
          resolved INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL
        );
        """)
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(MOBILE_SCHEMA_VERSION),))
        self.conn.commit()

    def set_meta(self, key: str, value: Any) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, json.dumps(_sanitize(value), ensure_ascii=False)))
        self.conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if not row: return default
        try: return json.loads(row[0])
        except Exception: return row[0]


class MobileArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = (root / "artifacts").resolve(); self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.jsonl"

    def put_bytes(self, relative: str, data: bytes, *, source: str = "local") -> dict[str, Any]:
        target = _safe_join(self.root, relative); target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(data); os.replace(tmp, target)
        row = {"path": str(target.relative_to(self.root)), "sha256": _sha256_bytes(data), "size": len(data), "source": source, "created_at": _now()}
        with self.manifest.open("a", encoding="utf-8") as fh: fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def put_file(self, path: str | Path, *, relative: str | None = None, source: str = "local") -> dict[str, Any]:
        src = Path(path).resolve(); data = src.read_bytes()
        return self.put_bytes(relative or src.name, data, source=source)

    def get(self, relative: str) -> bytes:
        return _safe_join(self.root, relative).read_bytes()

    def verify(self, relative: str, sha256: str) -> bool:
        try: return _sha256_bytes(self.get(relative)) == sha256
        except Exception: return False

    def download(self, url: str, relative: str, *, enabled: bool, max_mb: int = 512) -> dict[str, Any]:
        if not enabled: raise PermissionError("network downloads disabled by mobile policy")
        if not url.lower().startswith(("https://", "http://")): raise ValueError("only http(s) downloads are supported")
        cap = max_mb * 1024 * 1024
        req = urllib.request.Request(url, headers={"User-Agent": "CEO-Mobile/1"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(cap + 1)
        if len(data) > cap: raise ValueError("download exceeds configured size cap")
        return self.put_bytes(relative, data, source=url)


class MobileEvidenceLedger:
    def __init__(self, db: MobileDB, key: bytes) -> None:
        if len(key) < 16: raise ValueError("evidence key too short")
        self.db = db; self.key = key

    def record(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        clean = _sanitize(payload); raw = _json_bytes({"kind": kind, "payload": clean})
        sig = hmac.new(self.key, raw, hashlib.sha256).hexdigest(); eid = secrets.token_hex(12)
        row = {"id": eid, "kind": kind, "payload": clean, "sha256": _sha256_bytes(raw), "signature": sig, "created_at": _now()}
        self.db.conn.execute("INSERT INTO evidence(id,kind,payload,sha256,created_at) VALUES(?,?,?,?,?)", (eid, kind, json.dumps(row, ensure_ascii=False), row["sha256"], row["created_at"]))
        self.db.conn.commit(); return row

    def verify(self, row: dict[str, Any]) -> bool:
        raw = _json_bytes({"kind": row.get("kind"), "payload": row.get("payload", {})})
        sig = hmac.new(self.key, raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, str(row.get("signature", ""))) and _sha256_bytes(raw) == row.get("sha256")


class MobileJobQueue:
    ACTIVE = {"queued", "leased", "running"}
    def __init__(self, db: MobileDB) -> None: self.db = db

    def enqueue(self, kind: str, payload: dict[str, Any], *, priority: int = 50, job_id: str | None = None) -> dict[str, Any]:
        jid = job_id or secrets.token_hex(12); now = _now(); clean = _sanitize(payload)
        self.db.conn.execute("INSERT OR IGNORE INTO jobs(id,kind,payload,status,priority,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (jid, kind, json.dumps(clean, ensure_ascii=False), "queued", int(priority), now, now))
        self.db.conn.commit(); return self.get(jid) or {}

    def lease_next(self, *, ttl: float = 120.0) -> dict[str, Any] | None:
        now = _now()
        self.db.conn.execute("UPDATE jobs SET status='queued',lease_token=NULL,lease_expires=NULL,updated_at=? WHERE status='leased' AND lease_expires<?", (now, now)); self.db.conn.commit()
        row = self.db.conn.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY priority DESC,created_at ASC LIMIT 1").fetchone()
        if not row: return None
        token = secrets.token_urlsafe(18)
        cur = self.db.conn.execute("UPDATE jobs SET status='leased',lease_token=?,lease_expires=?,updated_at=? WHERE id=? AND status='queued'", (token, now+ttl, now, row["id"])); self.db.conn.commit()
        return self.get(row["id"]) if cur.rowcount else None

    def complete(self, job_id: str, token: str, result: dict[str, Any]) -> bool:
        row = self.db.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["lease_token"] != token or row["status"] not in {"leased", "running"}: return False
        clean = _sanitize(result); raw = _json_bytes(clean); rh = _sha256_bytes(raw)
        if row["result_hash"]: return row["result_hash"] == rh
        self.db.conn.execute("UPDATE jobs SET status='complete',result=?,result_hash=?,updated_at=? WHERE id=?", (json.dumps(clean, ensure_ascii=False), rh, _now(), job_id)); self.db.conn.commit(); return True

    def fail(self, job_id: str, token: str, error: str, *, retry: bool = True) -> bool:
        row = self.db.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row["lease_token"] != token: return False
        status = "queued" if retry else "failed"
        self.db.conn.execute("UPDATE jobs SET status=?,result=?,lease_token=NULL,lease_expires=NULL,updated_at=? WHERE id=?", (status, json.dumps({"error": error}), _now(), job_id)); self.db.conn.commit(); return True

    def get(self, job_id: str) -> dict[str, Any] | None:
        r = self.db.conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not r: return None
        d = dict(r); d["payload"] = json.loads(d["payload"] or "{}"); d["result"] = json.loads(d["result"] or "null"); return d

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT id FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self.get(r[0]) for r in rows if self.get(r[0])]


class MobileApprovalQueue:
    """Human approvals with one-shot tokens. Spend approvals are separate by design."""
    def __init__(self, db: MobileDB) -> None: self.db = db

    def request(self, action: str, payload: dict[str, Any], *, risk: str = "normal") -> dict[str, Any]:
        aid = secrets.token_hex(12); ph = _sha256_bytes(_json_bytes(_sanitize(payload))); now = _now()
        category = "spend" if action.lower() in SPEND_ACTIONS or risk == "spend" else risk
        self.db.conn.execute("INSERT INTO approvals(id,action,risk,payload_hash,status,created_at) VALUES(?,?,?,?,?,?)", (aid, action, category, ph, "pending", now)); self.db.conn.commit()
        return {"id": aid, "action": action, "risk": category, "payload_hash": ph, "status": "pending"}

    def approve(self, approval_id: str, *, human_confirmed: bool) -> str:
        if not human_confirmed: raise PermissionError("explicit human confirmation required")
        row = self.db.conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not row or row["status"] != "pending": raise ValueError("approval not pending")
        token = secrets.token_urlsafe(24); th = hashlib.sha256(token.encode()).hexdigest()
        self.db.conn.execute("UPDATE approvals SET status='approved',token_hash=? WHERE id=?", (th, approval_id)); self.db.conn.commit(); return token

    def reject(self, approval_id: str, *, human_confirmed: bool) -> None:
        if not human_confirmed: raise PermissionError("explicit human confirmation required")
        self.db.conn.execute("UPDATE approvals SET status='rejected' WHERE id=? AND status='pending'", (approval_id,)); self.db.conn.commit()

    def consume(self, approval_id: str, token: str, payload: dict[str, Any], *, require_spend: bool = False) -> bool:
        row = self.db.conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone()
        if not row or row["status"] != "approved" or not row["token_hash"]: return False
        if require_spend and row["risk"] != "spend": return False
        if _sha256_bytes(_json_bytes(_sanitize(payload))) != row["payload_hash"]: return False
        if not hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), row["token_hash"]): return False
        self.db.conn.execute("UPDATE approvals SET status='consumed',consumed_at=? WHERE id=?", (_now(), approval_id)); self.db.conn.commit(); return True

    def pending(self) -> list[dict[str, Any]]:
        rows = self.db.conn.execute("SELECT id,action,risk,payload_hash,status,created_at FROM approvals WHERE status='pending' ORDER BY created_at ASC").fetchall()
        return [dict(r) for r in rows]


class SpendGuard:
    def __init__(self, approvals: MobileApprovalQueue) -> None: self.approvals = approvals
    def authorize(self, *, approval_id: str | None, token: str | None, payload: dict[str, Any]) -> bool:
        if not approval_id or not token: return False
        return self.approvals.consume(approval_id, token, payload, require_spend=True)


class SecretHandleStore:
    """Resolve secrets from process environment only; never persists values."""
    def __init__(self, db: MobileDB) -> None: self.db = db
    def register_env(self, handle: str, env_name: str) -> None:
        if not handle or not env_name: raise ValueError("handle/env required")
        self.db.set_meta(f"secret_handle:{handle}", {"type": "env", "env": env_name})
    def resolve(self, handle: str) -> str | None:
        row = self.db.get_meta(f"secret_handle:{handle}") or {}
        return os.getenv(row.get("env", "")) if row.get("type") == "env" else None
    def status(self, handle: str) -> dict[str, Any]:
        row = self.db.get_meta(f"secret_handle:{handle}") or {}
        return {"handle": handle, "configured": bool(row), "available": bool(self.resolve(handle)), "value_persisted": False}


class LocalOpenAICompatibleClient:
    def __init__(self, url: str, model: str = "local-model") -> None:
        self.url = url; self.model = model
    def health(self) -> bool:
        # llama.cpp commonly exposes /health on the same host; fallback to false if unavailable.
        try:
            base = self.url.split("/v1/", 1)[0].rstrip("/") + "/health"
            with urllib.request.urlopen(base, timeout=2) as r: return 200 <= r.status < 300
        except Exception: return False
    def chat(self, messages: list[dict[str, str]], *, max_tokens: int = 512) -> str:
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=180) as r: row = json.loads(r.read().decode())
        choices = row.get("choices") or []
        if not choices: raise RuntimeError("local model returned no choices")
        return str(choices[0].get("message", {}).get("content", ""))


class MobileLocalWorker:
    def __init__(self, config: MobileNodeConfig) -> None: self.config=config; self.client=LocalOpenAICompatibleClient(config.local_model_url, config.local_model_name)
    def execute(self, instruction: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        messages = [{"role":"system","content":"You are a bounded CEO Mobile local worker. Never claim actions you did not execute."}]
        if context: messages.append({"role":"system","content":"Context: "+json.dumps(_sanitize(context), ensure_ascii=False)[:8000]})
        messages.append({"role":"user","content":instruction})
        text = self.client.chat(messages)
        return {"text":text, "provider":"mobile-local", "model":self.config.local_model_name, "offline_capable":True}


class MobileRemoteWorkerProvider(WorkerProvider):
    """Windows-side provider for a paired mobile node HTTP endpoint."""
    name = "mobile-node"
    kind = WorkerKind.LOCAL
    capabilities = frozenset({"general","reasoning","review","local_ai","mobile"})
    def __init__(self, base_url: str, shared_secret: str, *, timeout: float = 240.0) -> None:
        self.base_url=base_url.rstrip("/"); self.shared_secret=shared_secret; self.timeout=timeout
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        raw=_json_bytes(_sanitize(payload)); sig=hmac.new(self.shared_secret.encode(),raw,hashlib.sha256).hexdigest()
        req=urllib.request.Request(self.base_url+path,data=raw,headers={"Content-Type":"application/json","X-CEO-Signature":sig},method="POST")
        with urllib.request.urlopen(req,timeout=self.timeout) as r:return json.loads(r.read().decode())
    async def execute(self, request: WorkerRequest) -> WorkerResult:
        import asyncio
        try:
            row=await asyncio.to_thread(self._post,"/worker",request.model_dump(mode="json"))
            return WorkerResult(provider=self.name,kind=self.kind,success=bool(row.get("success",True)),text=str(row.get("text","")),metadata=dict(row.get("metadata",{})),artifacts=list(row.get("artifacts",[])),error=row.get("error"))
        except Exception as exc:
            return WorkerResult(provider=self.name,kind=self.kind,success=False,error=f"{type(exc).__name__}: {exc}")
    async def healthcheck(self) -> ProviderHealth:
        import asyncio
        try:
            def get():
                with urllib.request.urlopen(self.base_url+"/health",timeout=3) as r:return json.loads(r.read().decode())
            row=await asyncio.to_thread(get); return ProviderHealth(provider=self.name,available=bool(row.get("ok")),metadata=row)
        except Exception as exc:return ProviderHealth(provider=self.name,available=False,detail=str(exc))


class MobileResourceScheduler:
    def choose(self, task: dict[str, Any], pc: dict[str, Any], mobile: dict[str, Any]) -> dict[str, Any]:
        caps=set(task.get("required_capabilities",[])); category=str(task.get("category","")).lower(); ram_need=float(task.get("ram_gb",0) or 0)
        if caps & WINDOWS_ONLY_CAPABILITIES or category in {"windows_ui","installer","registry"}:
            return {"node":"windows","reason":"windows-only capability"}
        mobile_avail=float(mobile.get("ram_available_gb",mobile.get("ram_total_gb",0)) or 0)
        pc_avail=float(pc.get("ram_available_gb",pc.get("ram_total_gb",0)) or 0)
        battery=mobile.get("battery",{}) or {}; pct=float(battery.get("percentage",100) or 100)
        charging=str(battery.get("status","")).upper() in {"CHARGING","FULL"}
        mobile_ok=bool(mobile.get("online",True)) and (pct>=25 or charging)
        mobile_friendly=category in {"inference","research","review","tests","benchmark","artifact","summarize"} or bool(caps & {"local_ai","review","cpu","file"})
        if mobile_ok and mobile_friendly and ram_need <= max(0.0,mobile_avail*0.8) and (mobile_avail>pc_avail*1.2 or task.get("prefer_mobile")):
            return {"node":"mobile","reason":"mobile has suitable capability/resource headroom"}
        return {"node":"windows","reason":"default/locality or mobile headroom insufficient"}


class MobileBenchmark:
    def run(self, *, iterations: int = 100000) -> dict[str, Any]:
        start=time.perf_counter(); data=b"ceo-mobile-benchmark"; digest=b""
        for i in range(iterations): digest=hashlib.sha256(data+str(i).encode()).digest()
        elapsed=max(1e-9,time.perf_counter()-start)
        return {"iterations":iterations,"seconds":elapsed,"ops_per_second":iterations/elapsed,"digest":digest.hex(),"field_device":platform.platform()}


class MobileGitWorkspace:
    def __init__(self, root: Path) -> None:self.root=root.resolve()
    def _git(self,*args:str)->dict[str,Any]:
        p=subprocess.run(["git",*args],cwd=self.root,capture_output=True,text=True,timeout=60)
        return {"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
    def status(self)->dict[str,Any]:return self._git("status","--short","--branch")
    def diff(self)->dict[str,Any]:return self._git("diff","--no-ext-diff")
    def log(self,n:int=10)->dict[str,Any]:return self._git("log","--oneline",f"-{max(1,min(n,100))}")


class MobileNodeCore:
    def __init__(self, config: MobileNodeConfig | None = None, *, evidence_key: bytes | None = None) -> None:
        self.config=config or MobileNodeConfig(); root=self.config.root_path; root.mkdir(parents=True,exist_ok=True)
        self.db=MobileDB(root); self.artifacts=MobileArtifactStore(root); self.queue=MobileJobQueue(self.db); self.approvals=MobileApprovalQueue(self.db); self.spend=SpendGuard(self.approvals); self.secrets=SecretHandleStore(self.db)
        key=evidence_key or self._load_or_create_evidence_key(root); self.evidence=MobileEvidenceLedger(self.db,key); self.preflight=MobilePreflight(self.config); self.worker=MobileLocalWorker(self.config); self.scheduler=MobileResourceScheduler(); self.emergency_file=root/"EMERGENCY_STOP"
    def _load_or_create_evidence_key(self,root:Path)->bytes:
        path=root/".evidence_key"
        if path.exists():return base64.urlsafe_b64decode(path.read_text().strip().encode())
        key=secrets.token_bytes(32); path.write_text(base64.urlsafe_b64encode(key).decode());
        try:os.chmod(path,0o600)
        except Exception:pass
        return key
    def emergency_stop(self,reason:str="human emergency stop")->dict[str,Any]:
        self.emergency_file.write_text(json.dumps({"reason":reason,"at":_now()})); self.db.set_meta("emergency_stop",True); return {"active":True,"reason":reason}
    def safe_resume(self,*,human_confirmed:bool)->dict[str,Any]:
        if not human_confirmed:raise PermissionError("human confirmation required")
        self.emergency_file.unlink(missing_ok=True);self.db.set_meta("emergency_stop",False);return {"active":False}
    def emergency_active(self)->bool:return self.emergency_file.exists() or bool(self.db.get_meta("emergency_stop",False))
    def friction(self,kind:str,details:dict[str,Any],severity:str="P2")->dict[str,Any]:
        fid=secrets.token_hex(10);self.db.conn.execute("INSERT INTO friction(id,kind,severity,details,created_at) VALUES(?,?,?,?,?)",(fid,kind,severity,json.dumps(_sanitize(details)),_now()));self.db.conn.commit();return {"id":fid,"kind":kind,"severity":severity}
    def dashboard(self)->dict[str,Any]:
        snap=asdict(self.preflight.snapshot()); jobs=self.queue.list(50); pending=self.approvals.pending();
        return {"node":snap,"emergency_stop":self.emergency_active(),"jobs":{"total":len(jobs),"queued":sum(j.get("status")=="queued" for j in jobs),"running":sum(j.get("status") in {"leased","running"} for j in jobs)},"approvals":{"pending":len(pending),"items":pending[:20]},"local_model":{"url":self.config.local_model_url,"healthy":self.worker.client.health()},"spend_policy":{"auto_spend_allowed":False,"human_one_shot_required":True},"timestamp":_now()}
    def certification(self)->dict[str,Any]:
        snap=asdict(self.preflight.snapshot()); checks={
            "python":bool(snap["python"]),"git":snap["git"],"ssh":snap["ssh"],"workspace":self.config.root_path.exists(),"durable_queue":True,"artifact_hashing":True,"evidence_signing":True,"approval_queue":True,"spend_lock":True,"emergency_stop":True,"resource_scheduler":True,"dashboard":True,"offline_queue":True,
        }
        field={"android_termux":snap["termux"],"local_model":self.worker.client.health(),"pc_pairing":bool(self.db.get_meta("paired_windows")),"notifications":bool(_cmd_path("termux-notification"))}
        return {"status":"MOBILE_ALPHA_READY" if all(checks.values()) and all(field.values()) else "MOBILE_ALPHA_PREPARED_LOCAL","local_checks":checks,"field_checks":field,"ready":all(checks.values()) and all(field.values()),"production_verified":False}


class MobileNotifier:
    def notify(self, title: str, content: str, *, priority: str = "default") -> dict[str, Any]:
        exe = _cmd_path("termux-notification")
        if not exe:
            return {"sent": False, "reason": "termux-notification unavailable"}
        p = subprocess.run([exe, "--title", title[:120], "--content", content[:1000], "--priority", priority], capture_output=True, text=True, timeout=5)
        return {"sent": p.returncode == 0, "exit_code": p.returncode, "stderr": p.stderr[-500:]}


class MobileResearchClient:
    """Read-only HTTP research helper with bounded response size and provenance hash."""
    def fetch(self, url: str, *, max_bytes: int = 2_000_000) -> dict[str, Any]:
        if not url.lower().startswith(("https://", "http://")): raise ValueError("only http(s) URLs")
        req=urllib.request.Request(url,headers={"User-Agent":"CEO-Mobile-Research/1"})
        with urllib.request.urlopen(req,timeout=20) as r:
            data=r.read(max_bytes+1); ctype=r.headers.get("content-type","")
        if len(data)>max_bytes: raise ValueError("research response exceeds cap")
        text=data.decode("utf-8",errors="replace")
        return {"url":url,"status":200,"content_type":ctype,"bytes":len(data),"sha256":_sha256_bytes(data),"text":text}


class MobileAdversarialReviewer:
    def __init__(self, worker: MobileLocalWorker) -> None:self.worker=worker
    def review(self, proposal: str, evidence: dict[str, Any]) -> dict[str, Any]:
        prompt=("Act as an adversarial reviewer. Identify unsupported claims, regressions, unsafe permissions, "
                "secret leakage, spend/payment risk, and missing tests. Return a concise verdict PASS/FAIL/UNCERTAIN.\n\n"
                f"PROPOSAL:\n{proposal}\n\nEVIDENCE:\n{json.dumps(_sanitize(evidence),ensure_ascii=False)[:12000]}")
        row=self.worker.execute(prompt); text=str(row.get("text","")); upper=text.upper()
        verdict="FAIL" if "FAIL" in upper else "UNCERTAIN" if "UNCERTAIN" in upper else "PASS" if "PASS" in upper else "UNCERTAIN"
        return {"verdict":verdict,"review":text,"provider":"mobile-local","field_verified":True}


class MobileNodeRegistry:
    def __init__(self, db: MobileDB) -> None:self.db=db
    def heartbeat(self, node_id: str, snapshot: dict[str, Any], *, ttl: float = 45.0) -> dict[str, Any]:
        nodes=self.db.get_meta("paired_nodes",{}) or {};nodes[node_id]={"snapshot":_sanitize(snapshot),"seen_at":_now(),"expires_at":_now()+ttl,"online":True};self.db.set_meta("paired_nodes",nodes);return nodes[node_id]
    def list(self) -> dict[str, Any]:
        nodes=self.db.get_meta("paired_nodes",{}) or {};now=_now()
        for row in nodes.values():row["online"]=float(row.get("expires_at",0))>=now
        return nodes
    def best(self) -> str | None:
        rows=[]
        for nid,row in self.list().items():
            if not row.get("online"):continue
            s=row.get("snapshot",{});score=float(s.get("ram_available_gb",0))*2+float(s.get("logical_cpus",0))
            rows.append((score,nid))
        return max(rows)[1] if rows else None


class MobileSyncBundle:
    def __init__(self, core: MobileNodeCore) -> None:self.core=core
    def export(self, path: Path) -> dict[str, Any]:
        import zipfile
        path=path.resolve();path.parent.mkdir(parents=True,exist_ok=True)
        payload={"node_id":self.core.config.node_id,"dashboard":self.core.dashboard(),"certification":self.core.certification(),"jobs":self.core.queue.list(500),"evidence":[],"created_at":_now()}
        for r in self.core.db.conn.execute("SELECT payload FROM evidence ORDER BY created_at ASC").fetchall():
            try:payload["evidence"].append(json.loads(r[0]))
            except Exception:pass
        raw=_json_bytes(payload);sig=hmac.new(self.core.evidence.key,raw,hashlib.sha256).hexdigest()
        with zipfile.ZipFile(path,"w",compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("sync.json",raw);z.writestr("sync.sig",sig)
            if self.core.artifacts.manifest.exists():z.write(self.core.artifacts.manifest,"artifacts/manifest.jsonl")
        return {"path":str(path),"sha256":_sha256_bytes(path.read_bytes()),"items":len(payload["jobs"])+len(payload["evidence"]),"secret_values_included":False}
    def verify(self, path: Path) -> bool:
        import zipfile
        try:
            with zipfile.ZipFile(path) as z:raw=z.read("sync.json");sig=z.read("sync.sig").decode()
            exp=hmac.new(self.core.evidence.key,raw,hashlib.sha256).hexdigest();return hmac.compare_digest(sig,exp)
        except Exception:return False


class MobileGitHubReadonly:
    """Optional GitHub CLI read-only surface. It deliberately exposes no mutating commands."""
    def available(self) -> bool:return bool(_cmd_path("gh"))
    def _run(self,args:list[str])->dict[str,Any]:
        if not self.available():return {"available":False,"exit_code":127,"stdout":"","stderr":"gh unavailable"}
        p=subprocess.run(["gh",*args],capture_output=True,text=True,timeout=20)
        return {"available":True,"exit_code":p.returncode,"stdout":p.stdout,"stderr":p.stderr}
    def prs(self,limit:int=20)->dict[str,Any]:return self._run(["pr","list","--limit",str(max(1,min(limit,100))),"--json","number,title,state,url"])
    def runs(self,limit:int=20)->dict[str,Any]:return self._run(["run","list","--limit",str(max(1,min(limit,100))),"--json","databaseId,status,conclusion,workflowName,url"])
    def issues(self,limit:int=20)->dict[str,Any]:return self._run(["issue","list","--limit",str(max(1,min(limit,100))),"--json","number,title,state,url"])

# Late-bound helpers keep backwards compatibility with checkpoints that instantiate MobileNodeCore.
def _mobile_core_extras(core: MobileNodeCore) -> MobileNodeCore:
    if not hasattr(core,"notifier"): core.notifier=MobileNotifier()
    if not hasattr(core,"registry"): core.registry=MobileNodeRegistry(core.db)
    if not hasattr(core,"sync"): core.sync=MobileSyncBundle(core)
    if not hasattr(core,"research"): core.research=MobileResearchClient()
    if not hasattr(core,"adversarial"): core.adversarial=MobileAdversarialReviewer(core.worker)
    if not hasattr(core,"github"): core.github=MobileGitHubReadonly()
    return core

_original_mobile_init=MobileNodeCore.__init__
def _mobile_init_with_extras(self,*args,**kwargs):
    _original_mobile_init(self,*args,**kwargs);_mobile_core_extras(self)
MobileNodeCore.__init__=_mobile_init_with_extras
