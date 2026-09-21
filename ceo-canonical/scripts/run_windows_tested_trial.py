from __future__ import annotations
import asyncio, json, os, secrets, shutil, tempfile
from pathlib import Path
import sys

# Ensure the project root is importable when this file is executed directly from scripts/.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import psutil
from ceo_core.browser_worker import BrowserChatConfig, BrowserChatTransport
from ceo_core.credentials import WindowsCredentialManagerStore, WindowsDPAPISecretStore
from ceo_core.models import ProjectState
from ceo_core.resource_adaptive import CapacityProfiler, GPUProbe
from ceo_core.resource_governor import ResourceGovernor

def require_windows():
    if os.name != 'nt':
        raise SystemExit('TESTED Windows trial must run on Windows.')

async def browser_health()->dict:
    exe=(os.getenv('CEO_CHROMIUM_EXECUTABLE') or shutil.which('chrome') or shutil.which('msedge') or shutil.which('chromium'))
    with tempfile.TemporaryDirectory() as td:
        cfg=BrowserChatConfig(name='windows-tested-browser',start_url='about:blank',input_selector='#x',send_selector='#s',assistant_selector='#a',profile_dir=str(Path(td)/'profile'),registry_path=str(Path(td)/'reg.json'),executable_path=exe,headless=True)
        h=await BrowserChatTransport(cfg).healthcheck()
        return {'passed':h.available,'detail':h.detail,'executable':exe}

async def main():
    require_windows()
    outdir=Path(os.getenv('CEO_TEST_OUT') or 'reports/windows-tested').resolve(); outdir.mkdir(parents=True,exist_ok=True)
    state=ProjectState(goal='Windows TESTED trial')
    governor=ResourceGovernor(); prof=CapacityProfiler(governor)
    cap=prof.profile(state)
    capacity=cap.__dict__ if hasattr(cap,'__dict__') else {k:getattr(cap,k) for k in cap.__slots__}
    resource={'snapshot':governor.snapshot(),'scenarios':{str(p):governor.limits(p) for p in (20,50,80,95)},'capacity':capacity,'gpu':GPUProbe().snapshot()}
    key='tested-'+secrets.token_hex(6); secret='CEO-'+secrets.token_hex(12)
    dp=WindowsDPAPISecretStore(); dp.put(key,secret); dp_ok=dp.get(key)==secret; dp.delete(key)
    cm=WindowsCredentialManagerStore(namespace='CEO-de-IAs-Tested'); cm.put(key,secret); cm_ok=cm.get(key)==secret; cm.delete(key)
    browser=await browser_health()
    report={
      'phase':'TESTED_ONLY','records_validation_registry':False,
      'environment':{'platform':'windows','logical_cpus':psutil.cpu_count(logical=True),'ram_gb':round(psutil.virtual_memory().total/1024**3,2)},
      'resource_governor':resource,
      'credentials':{'dpapi_roundtrip':dp_ok,'credential_manager_roundtrip':cm_ok},
      'browser':browser,
      'passed':bool(dp_ok and cm_ok and browser['passed'])
    }
    out=outdir/'WINDOWS_TESTED_TRIAL.json'; out.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print(out); print(json.dumps(report,indent=2,default=str))
    raise SystemExit(0 if report['passed'] else 1)

if __name__=='__main__': asyncio.run(main())
