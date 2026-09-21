from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ceo_core.desktop_integration import (
    ApplicationRegistry, ApplicationCapabilityDiscovery, BrowserDownloadManager,
    ChromeSessionManager, DesktopBrowserIntegrationCore, VisualFallbackController,
    VisualTarget,
)
from ceo_core.models import ProjectState


class Finder:
    def __call__(self, candidate: str):
        names={"chrome.exe":"C:/Apps/Chrome/chrome.exe","explorer.exe":"C:/Windows/explorer.exe","wt.exe":"C:/Windows/wt.exe","code":"C:/Apps/VSCode/code.exe"}
        return names.get(candidate)


class Visual:
    def __init__(self): self.actions=[]
    def screenshot(self): return b"screen"
    def click(self,x,y): self.actions.append((x,y))
    def type_text(self,text): self.actions.append(("type",len(text)))
    def press(self,key): self.actions.append(("key",key))


def main():
    s=ProjectState(id="bench-desktop",goal="desktop benchmark")
    reg=ApplicationRegistry(); reg.initialize(s); found=reg.discover(s,finder=Finder())
    discovery=ApplicationCapabilityDiscovery(reg)
    browse_rank=discovery.rank(s,["browse","tabs","download"])

    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        sessions=ChromeSessionManager(root/"profiles")
        for i in range(1000):
            sessions.get_or_create(s,f"session-{i%25}")
        session_count=len(s.metadata.get(sessions.KEY,{}))
        profiles_exist=all(Path(x.profile_dir).is_dir() for x in sessions.list(s))

        dl=BrowserDownloadManager()
        for i in range(250):
            p=root/f"d-{i}.txt"; p.write_text(f"payload-{i}",encoding="utf-8")
            dl.register(s,p,source_url=f"https://example.test/{i}")
        download_hashes_unique=len({x["sha256"] for x in s.metadata[dl.KEY]})==250

    visual=Visual(); fallback=VisualFallbackController(visual,lambda img,desc: VisualTarget(4,5,.95,desc))
    blocked_before=fallback.act(s,description="Save",structured_failed=False,approved=True)
    blocked_unapproved=fallback.act(s,description="Save",structured_failed=True,approved=False)
    allowed=fallback.act(s,description="Save",structured_failed=True,approved=True)

    core=DesktopBrowserIntegrationCore(reg)
    preflight=core.local_preflight(s)
    result={
        "applications_declared":len(found),
        "applications_discovered":sum(int(x.discovered) for x in found),
        "browse_top":browse_rank[0]["app_id"] if browse_rank else None,
        "session_operations":1000,
        "distinct_sessions":session_count,
        "profiles_exist":profiles_exist,
        "downloads_registered":len(s.metadata.get(dl.KEY,[])),
        "download_hashes_unique":download_hashes_unique,
        "visual_guard_structured_first":blocked_before.get("reason")=="structured_control_must_fail_first",
        "visual_guard_approval":blocked_unapproved.get("reason")=="visual_fallback_requires_approval",
        "visual_allowed_after_both_gates":allowed.get("ok") is True,
        "local_preflight":preflight,
        "windows_physical":"DEFERRED_BY_USER",
        "chrome_physical":"DEFERRED_BY_USER",
    }
    result["pass"]=all([
        result["applications_declared"]>=4,
        result["applications_discovered"]>=4,
        result["browse_top"]=="chrome",
        result["distinct_sessions"]==25,
        result["profiles_exist"],
        result["downloads_registered"]==250,
        result["download_hashes_unique"],
        result["visual_guard_structured_first"],
        result["visual_guard_approval"],
        result["visual_allowed_after_both_gates"],
        preflight["pass"],
    ])
    print(json.dumps(result,indent=2,sort_keys=True))

if __name__=="__main__": main()
