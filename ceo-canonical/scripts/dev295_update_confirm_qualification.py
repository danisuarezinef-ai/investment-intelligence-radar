from __future__ import annotations

import json
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from ceo_core.credentials import MemorySecretStore
from ceo_core.internal_release_coordinator import InternalReleaseCoordinator, InternalReleaseRequest
from ceo_core.internal_release_publisher import InternalReleasePublisher
from ceo_core.release_signing_authority import ReleaseSigningAuthority

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)


def candidate(path: Path, version: str) -> None:
    contract={"contract_version":1,"app_version":version,"data_schema_version":1,"launcher":"ABRIR_CEO.cmd","required_paths":["ABRIR_CEO.cmd","CEO_UPDATE_PACKAGE.json"],"file_hashes":{}}
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("ABRIR_CEO.cmd","@echo off\r\n")
        z.writestr("CEO_UPDATE_PACKAGE.json",json.dumps(contract))


def main() -> int:
    checks=[]
    def ck(name, cond, detail=""):
        checks.append({"name":name,"pass":bool(cond),"detail":detail})
        if not cond: raise AssertionError(name+": "+detail)

    goodq={"tests_passed":True,"clean_extract_passed":True,"package_contract_passed":True,"security_passed":True,"failed_tests":0,"security_findings":0,"local_candidate_ready":True}
    badq=dict(goodq);badq["security_findings"]=1
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); bare=td/"remote.git"; work=td/"seed"; pkg=td/"CEO_9.9.1-test.zip"
        run("git","init","--bare",str(bare))
        run("git","init",str(work));run("git","config","user.email","test@example.invalid",cwd=work);run("git","config","user.name","test",cwd=work)
        (work/"ceo-updates").mkdir();(work/"ceo-updates"/"manifest.json").write_text(json.dumps({"release_sequence":294,"version":"1.5.70"}),encoding="utf-8")
        run("git","add",".",cwd=work);run("git","commit","-m","seed",cwd=work);run("git","branch","-M","ceo-update-channel",cwd=work);run("git","remote","add","origin",str(bare),cwd=work);run("git","push","-u","origin","ceo-update-channel",cwd=work)
        run("git","symbolic-ref","HEAD","refs/heads/ceo-update-channel",cwd=bare)
        candidate(pkg,"9.9.1-test")
        auth=ReleaseSigningAuthority(MemorySecretStore());auth.ensure_key()
        class LocalPolicy:
            standing_publication_authorization=True
            install_requires_human_confirmation=True
            allow_key_rotation=False
            path_prefix="ceo-updates/"
            branch="ceo-update-channel"
            repository="local/test"
            def allows(self, *, repository, branch, path):
                return repository==self.repository and branch==self.branch and str(path).startswith(self.path_prefix)
        policy=LocalPolicy()
        pub=InternalReleasePublisher(authority=auth,policy=policy,receipt_root=td/"publisher-receipts",transport_repo_url=str(bare),urlopen=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("remote http unused in local transport")))
        # Local transport cannot use raw.githubusercontent remote verification, so patch only that network edge.
        pub._remote_verify=lambda manifest,**kwargs: True
        coord=InternalReleaseCoordinator(root=td/"coord",publisher=pub,poll_seconds=5)
        rejected=coord.enqueue(InternalReleaseRequest(str(pkg),"9.9.1-test",295,"dev295-test","test","1.5.58",badq))
        ck("qualification_fail_closed",rejected["status"]=="QUALIFICATION_REJECTED")
        queued=coord.enqueue(InternalReleaseRequest(str(pkg),"9.9.1-test",295,"dev295-test","test","1.5.58",goodq))
        ck("qualified_candidate_queued",queued["ok"] and queued["status"]=="QUEUED")
        rows=coord.scan_once();ck("automatic_publish_scan",rows and rows[0].get("status")=="PUBLISHED",str(rows))
        st=coord.status();ck("queue_drained",len(st["queued"])==0);ck("install_still_manual",st["automatic_installation"] is False and st["operator_install_confirmation_required"] is True)
        # anti-replay / duplicate request stays fail-closed
        queued2=coord.enqueue(InternalReleaseRequest(str(pkg),"9.9.1-test",295,"dev295-test2","test","1.5.58",goodq));ck("duplicate_can_queue",queued2["ok"])
        rows2=coord.scan_once();ck("anti_replay",rows2 and rows2[0].get("status")=="ANTI_REPLAY_BLOCKED",str(rows2))

    print(json.dumps({"ok":all(x["pass"] for x in checks),"checks":checks},indent=2))
    return 0

if __name__=="__main__": raise SystemExit(main())
