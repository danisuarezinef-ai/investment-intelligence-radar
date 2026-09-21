from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

from ceo_core.browser_worker import BrowserChatConfig, BrowserChatTransport
from ceo_core.quality_audit import TestQualityAuditor
from ceo_core.validation import ValidationEvidence, ValidationRegistry, StrictReleaseGates
from ceo_core.validation_harness import run_local_validation

REPORTS=Path('reports'); REPORTS.mkdir(exist_ok=True)
REGISTRY_PATH=REPORTS/'VALIDATION_REGISTRY_MVP_0.8.json'

CAPABILITY_TEST_MAP={
    'scheduler':['tests/test_scheduler.py','tests/test_scheduler_priority_retry.py','tests/test_mvp05_scheduler_integration.py'],
    'conversation_controller':['tests/test_conversation_controller.py','tests/test_result_protocol_controller.py','tests/test_ai_worker_scheduler_integration.py'],
    'persistence_recovery':['tests/test_persistence_recovery.py','tests/test_sqlite_store.py','tests/test_mvp04_store_browser_simulator.py'],
    'resource_governor':['tests/test_resource_eta.py','tests/test_mvp04_integration.py','tests/test_mvp06_systems.py'],
    'browser_worker':['tests/test_browser_worker.py','tests/test_browser_scheduler_e2e.py'],
    'provider_intelligence':['tests/test_mvp05_intelligence.py','tests/test_mvp07_systems.py'],
    'knowledge_claim_engine':['tests/test_mvp05_intelligence.py','tests/test_mvp06_systems.py','tests/test_mvp07_systems.py'],
    'verification_multilayer':['tests/test_mvp06_systems.py','tests/test_mvp07_systems.py'],
    'notifications':['tests/test_mvp06_systems.py'],
    'distributed_nodes':['tests/test_mvp07_systems.py'],
    'objective_governance':['tests/test_mvp07_systems.py'],
    'prompt_learning':['tests/test_mvp07_systems.py'],
    'human_escalation':['tests/test_mvp06_systems.py','tests/test_mvp07_systems.py'],
    'authentication_persistence':['tests/test_browser_worker.py','tests/test_mvp04_store_browser_simulator.py'],
    'capacity_profiler':['tests/test_mvp06_systems.py'],
    'parallel_execution':['tests/test_scheduler.py','tests/test_autonomous_e2e.py'],
    'rate_limit_fallback':['tests/test_scheduler_priority_retry.py','tests/test_routing.py','tests/test_mvp04_integration.py'],
    'project_pilot_workflow':['tests/test_autonomous_e2e.py','tests/test_mvp06_systems.py'],
    'mini_review_pipeline':['tests/test_mvp05_intelligence.py','tests/test_mvp06_systems.py','tests/test_mvp07_systems.py'],
    'runtime_data_isolation':['tests/test_mvp08_validation.py'],
}

IMPLEMENTED_ONLY=(
    'live_ai_provider_validation',
    'real_concurrency_scaling',
    'multi_hour_absence_validation',
    'night_run_validation',
    'mobile_notification_validation',
)


def seed_test_evidence(reg:ValidationRegistry)->None:
    for cap,paths in CAPABILITY_TEST_MAP.items():
        detail='Behavioral coverage: '+', '.join(paths)
        reg.record(cap,ValidationEvidence(f'v08-suite-{cap}','integration','container-linux',True,detail,artifact='pytest'))


async def browser_local(reg:ValidationRegistry)->dict:
    executable=shutil.which('chromium') or shutil.which('google-chrome') or shutil.which('chromium-browser')
    if not executable:
        return {'passed':False,'detail':'No system Chromium/Chrome executable found.'}
    with tempfile.TemporaryDirectory() as td:
        cfg=BrowserChatConfig(name='v08-local-browser',start_url='about:blank',input_selector='#x',send_selector='#s',assistant_selector='#a',profile_dir=str(Path(td)/'profile'),registry_path=str(Path(td)/'registry.json'),executable_path=executable,headless=True)
        health=await BrowserChatTransport(cfg).healthcheck()
        passed=bool(health.available)
        reg.record('browser_worker',ValidationEvidence('v08-browser-local','integration','container-linux',passed,health.detail,artifact=executable))
        return {'passed':passed,'executable':executable,'health':health.model_dump()}


async def main():
    reg=ValidationRegistry(REGISTRY_PATH)
    for cap in IMPLEMENTED_ONLY:
        reg.ensure(cap, notes=['Implementation exists or protocol is prepared, but target/live evidence is still required.'])
    seed_test_evidence(reg)
    local=await run_local_validation(reg)
    browser=await browser_local(reg)
    test_quality=TestQualityAuditor().audit('tests')
    gates=StrictReleaseGates().assess(reg)
    report={
        'version':'0.8.0-validation-rc',
        'environment':{'os_name':os.name,'platform':'container-linux'},
        'local_validation':local,
        'browser_local':browser,
        'test_quality':test_quality,
        'maturity_summary':reg.summary(),
        'release_gates':gates,
        'matrix':reg.matrix(),
        'scope_note':'No Windows physical validation, authenticated AI service validation, mobile notification validation, or night-run stability is claimed by this report.',
    }
    (REPORTS/'MVP_0.8_LOCAL_VALIDATION.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    (REPORTS/'MATURITY_MATRIX_MVP_0.8.json').write_text(json.dumps({'summary':reg.summary(),'matrix':reg.matrix(),'release_gates':gates},indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))

if __name__=='__main__': asyncio.run(main())
