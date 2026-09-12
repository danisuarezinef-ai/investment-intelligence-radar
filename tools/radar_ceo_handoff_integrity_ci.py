"""Static fail-closed integrity gate for Radar autonomous CEO handoff."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
module_path=ROOT/'radar_ceo_handoff_v1.py'
cloud_path=ROOT/'cloud_service_v9.py'
workflow_path=ROOT/'.github/workflows/autonomous-paper-production-audit.yml'
assert module_path.exists() and cloud_path.exists() and workflow_path.exists()
module=module_path.read_text(encoding='utf-8')
cloud=cloud_path.read_text(encoding='utf-8')
workflow=workflow_path.read_text(encoding='utf-8')
tree=ast.parse(module)
assignments={}
for node in tree.body:
    if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
        try: assignments[node.targets[0].id]=ast.literal_eval(node.value)
        except Exception: pass
assert assignments.get('REAL_TRADING') is False
assert assignments.get('SNAPSHOT_KIND')=='radar_ceo_handoff_v1'
assert assignments.get('DATA_CONTRACT')=='DECISION_MEMORY_V1'
functions={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
for fn in ('memory_health','data_completeness','shadow_brain_registry','threshold_experiment','horizon_watch','executive_summary','build_handoff'):
    assert fn in functions, fn
assert "'development_mode':'MAINTENANCE_ONLY'" in module
assert "'primary_human_project':'CEO_DE_IAS'" in module
assert "'feature_expansion':False" in module
assert "'retroactive_fill_forbidden':True" in module
assert "'backfill_allowed':False" in module and "'acceleration_allowed':False" in module
assert "'changes_execution_policy':False" in module
assert 'import radar_ceo_handoff_v1 as ceo_handoff' in cloud
assert "'/autonomous-simulator/ceo-handoff-v1'" in cloud
assert "'/autonomous-simulator/executive-v1'" in cloud
assert "out['dashboard_contract']='AUTONOMOUS_SIMULATOR_V4'" in cloud
assert "out['development_mode']='MAINTENANCE_ONLY'" in cloud
assert 'autonomous-simulator/ceo-handoff-v1' in workflow
assert 'MAINTENANCE_ONLY' in workflow
version=json.loads((ROOT/'version.json').read_text(encoding='utf-8-sig'))
assert version.get('version')=='1.5.28'
assert 'exec python cloud_service_v9.py' in (ROOT/'start.sh').read_text(encoding='utf-8')
print(json.dumps({'status':'PASS','scope':'RADAR_CEO_HANDOFF','development_mode':'MAINTENANCE_ONLY','primary_human_project':'CEO_DE_IAS','setup_built':False,'real_trading':False},sort_keys=True))