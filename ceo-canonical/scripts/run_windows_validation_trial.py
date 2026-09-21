from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path

import psutil

from ceo_core.browser_worker import BrowserChatConfig, BrowserChatTransport
from ceo_core.credentials import WindowsCredentialManagerStore, WindowsDPAPISecretStore
from ceo_core.models import ProjectState
from ceo_core.resource_adaptive import CapacityProfiler, GPUProbe
from ceo_core.resource_governor import ResourceGovernor
from ceo_core.runtime import user_data_root
from ceo_core.validation import ValidationEvidence, ValidationRegistry, StrictReleaseGates


def require_windows():
    if os.name != 'nt':
        raise SystemExit('This validation must be executed on the target Windows PC. No physical validation was recorded.')


async def browser_health(data_root:Path)->dict:
    exe=os.getenv('CEO_CHROMIUM_EXECUTABLE') or shutil.which('chrome') or shutil.which('msedge') or shutil.which('chromium')
    with tempfile.TemporaryDirectory() as td:
        cfg=BrowserChatConfig(name='windows-physical-browser',start_url='about:blank',input_selector='#x',send_selector='#s',assistant_selector='#a',profile_dir=str(Path(td)/'profile'),registry_path=str(Path(td)/'reg.json'),executable_path=exe,headless=True)
        h=await BrowserChatTransport(cfg).healthcheck()
        return {'passed':h.available,'detail':h.detail,'executable':exe}


async def main():
    require_windows()
    data=user_data_root();data.mkdir(parents=True,exist_ok=True)
    reg=ValidationRegistry(data/'validation_registry.json')
    state=ProjectState(goal='Windows physical validation')
    governor=ResourceGovernor();prof=CapacityProfiler(governor)
    resource={'snapshot':governor.snapshot(),'scenarios':{str(p):governor.limits(p) for p in (20,50,80,95)},'capacity':prof.profile(state).__dict__ if hasattr(prof.profile(state),'__dict__') else {k:getattr(prof.profile(state),k) for k in prof.profile(state).__slots__},'gpu':GPUProbe().snapshot()}
    reg.record('resource_governor',ValidationEvidence('windows-resource','physical','windows-target',True,json.dumps(resource,default=str)))

    secret='CEO-'+secrets.token_hex(12);key='validation-'+secrets.token_hex(6)
    dp=WindowsDPAPISecretStore();dp.put(key,secret);dp_ok=dp.get(key)==secret;dp.delete(key)
    cm=WindowsCredentialManagerStore(namespace='CEO-de-IAs-Validation');cm.put(key,secret);cm_ok=cm.get(key)==secret;cm.delete(key)
    credentials={'dpapi_roundtrip':dp_ok,'credential_manager_roundtrip':cm_ok}
    reg.record('credential_storage',ValidationEvidence('windows-secrets','physical','windows-target',dp_ok and cm_ok,json.dumps(credentials)))

    browser=await browser_health(data)
    reg.record('browser_worker',ValidationEvidence('windows-browser','physical','windows-target',bool(browser['passed']),json.dumps(browser)))

    report={'environment':{'platform':'windows','logical_cpus':psutil.cpu_count(logical=True),'ram_gb':round(psutil.virtual_memory().total/1024**3,2)},'resource_governor':resource,'credentials':credentials,'browser':browser,'release_gates':StrictReleaseGates().assess(reg),'matrix':reg.matrix()}
    out=data/'WINDOWS_PHYSICAL_VALIDATION.json';out.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8');print(out);print(json.dumps(report,indent=2,default=str))

if __name__=='__main__':asyncio.run(main())
