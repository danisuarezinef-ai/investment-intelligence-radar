"""Static fail-closed integrity gate for Radar autonomous CEO handoff."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
module_path=ROOT/'radar_ceo_handoff_v1.py'
cloud_path=ROOT/'cloud_service_v9.py'
workflow_path=ROOT/'.github/workflows/autonomous-paper-production-audit.yml'
forward_path=ROOT/'radar_forward_engine.py'
taxonomy_path=ROOT/'radar_asset_taxonomy_v1.py'
proof_path=ROOT/'radar_pre160_production_proof_v1.py'
assert all(p.exists() for p in (module_path,cloud_path,workflow_path,forward_path,taxonomy_path,proof_path))
module=module_path.read_text(encoding='utf-8')
cloud=cloud_path.read_text(encoding='utf-8')
workflow=workflow_path.read_text(encoding='utf-8')
forward=forward_path.read_text(encoding='utf-8')
taxonomy=taxonomy_path.read_text(encoding='utf-8')
proof=proof_path.read_text(encoding='utf-8')
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
assert "'legacy_rows_do_not_block_new_contract_capture':True" in module
assert "'backfill_allowed':False" in module and "'acceleration_allowed':False" in module
assert "'changes_execution_policy':False" in module
assert 'DECISION_MEMORY_CONTRACT=\'DECISION_MEMORY_V1\'' in forward
assert "'prospective_capture':True" in forward and "'retroactive_fill':False" in forward
assert "'execution_holding_duration_verified':False" in forward
assert 'RADAR_INTERNAL_TAXONOMY_V1' in taxonomy and 'external_vendor_claim' in taxonomy
assert "'radar_forward_engine.py'" in proof and "'radar_asset_taxonomy_v1.py'" in proof
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
print(json.dumps({'status':'PASS','scope':'RADAR_CEO_HANDOFF','development_mode':'MAINTENANCE_ONLY','primary_human_project':'CEO_DE_IAS','prospective_memory_contract':'DECISION_MEMORY_V1','setup_built':False,'real_trading':False},sort_keys=True))