from __future__ import annotations
import hashlib, json, tempfile, time, urllib.request
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse
from .internal_release_publisher import InternalReleasePublisher
from .update_channel import official_channel
class PreparedReleaseBridge:
    def __init__(self,publisher:InternalReleasePublisher|None=None):
        self.publisher=publisher or InternalReleasePublisher(); self.channel=official_channel()
    def _allowed(self,url:str)->bool:
        p=urlparse(str(url or "")); prefix=f"/{self.channel.intended_repository}/{self.publisher.policy.branch}/{self.publisher.policy.path_prefix}"
        return p.scheme=="https" and p.netloc=="raw.githubusercontent.com" and p.path.startswith(prefix)
    @staticmethod
    def _fetch(url:str,timeout:int=60)->bytes:
        sep="&" if "?" in url else "?"; req=urllib.request.Request(url+sep+f"ceo_prepared={int(time.time())}",headers={"User-Agent":"CEO-de-IAs-PreparedRelease/1","Cache-Control":"no-cache, no-store","Pragma":"no-cache"})
        with urllib.request.urlopen(req,timeout=timeout) as resp:return resp.read()
    def activate(self,manifest_url:str)->dict:
        if not self._allowed(manifest_url):return {"ok":False,"status":"PREPARED_URL_REJECTED"}
        try: payload=json.loads(self._fetch(manifest_url,30).decode("utf-8"))
        except Exception as exc:return {"ok":False,"status":"PREPARED_MANIFEST_READ_FAILED","detail":f"{type(exc).__name__}: {exc}"[:600]}
        package_url=str(payload.get("url") or "")
        if not self._allowed(package_url):return {"ok":False,"status":"PREPARED_PACKAGE_URL_REJECTED"}
        try:
            size=int(payload.get("size_bytes") or 0); sha=str(payload.get("sha256") or "").lower()
            if size<=0 or len(sha)!=64:raise ValueError("invalid package identity")
            data=self._fetch(package_url,180)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:return {"ok":False,"status":"PREPARED_PACKAGE_MISMATCH"}
            with tempfile.TemporaryDirectory(prefix="ceo-prepared-release-") as td:
                package=Path(td)/str(payload.get("artifact_name") or Path(urlparse(package_url).path).name); package.write_bytes(data)
                qualification = payload.get("qualification")
                if not isinstance(qualification, dict):
                    return {
                        "ok": False,
                        "status": "PREPARED_QUALIFICATION_MISSING",
                        "detail": "Stable prepared releases require embedded production qualification.",
                    }
                result=self.publisher.publish(
                    package_path=package,
                    version=str(payload.get("version") or ""),
                    release_sequence=int(payload.get("release_sequence") or 0),
                    release_id=str(payload.get("release_id") or ""),
                    notes=str(payload.get("notes") or ""),
                    min_app_version=str(payload.get("min_app_version") or ""),
                    qualification=qualification,
                )
                row=asdict(result); row["automatic_installation"]=False; row["operator_install_confirmation_required"]=True; return row
        except Exception as exc:return {"ok":False,"status":"PREPARED_RELEASE_FAILED","detail":f"{type(exc).__name__}: {exc}"[:800]}
