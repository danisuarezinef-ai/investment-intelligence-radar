"""Static fail-closed integrity gate for Autonomous PAPER priorities 41-60."""
from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
module_path=ROOT/'radar_autonomous_learning_41_60_v1.py'
cloud_path=ROOT/'cloud_service_v9.py'
assert module_path.exists(), 'missing radar_autonomous_learning_41_60_v1.py'
assert cloud_path.exists(), 'missing cloud_service_v9.py'

module=module_path.read_text(encoding='utf-8')
cloud=cloud_path.read_text(encoding='utf-8')
tree=ast.parse(module)

assignments={}
for node in tree.body:
    if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
        try: assignments[node.targets[0].id]=ast.literal_eval(node.value)
        except Exception: pass
assert assignments.get('REAL_TRADING') is False
assert assignments.get('SNAPSHOT_KIND')=='autonomous_learning_41_60_v1'
assert assignments.get('COMBINED_KIND')=='autonomous_learning_16_60_v1'

required_functions={
    'calibration_quality','calibration_drift_guard','confidence_uncertainty_guard',
    'abstention_quality_guard','downside_tail_risk','cost_sensitivity','benchmark_robustness',
    'decay_guard','ranking_guard','anti_overfit_diagnostic','empirical_stress',
    'manual_promotion_gate','dashboard_v3','build_priorities_41_60',
}
functions={n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
missing=required_functions-functions
assert not missing, f'missing functions: {sorted(missing)}'

for task in range(41,59):
    assert f"'{task}':" in module or f'"{task}":' in module, f'missing task {task}'
assert "tasks['59']=" in module, 'missing task 59'
assert "tasks['60']=" in module, 'missing task 60'
assert "'automatic_promotion':False" in module or '"automatic_promotion":False' in module
assert "'automatic_release':False" in module or '"automatic_release":False' in module
assert "'live_execution_allowed':False" in module or '"live_execution_allowed":False' in module
assert "'horizon_backfill_allowed':False" in module
assert "'horizon_acceleration_allowed':False" in module
assert "'dashboard_contract':'AUTONOMOUS_SIMULATOR_V3'" in module
assert "'banner':'SIMULATION ONLY — NO REAL MONEY'" in module
assert "'manual_review_only':True" in module
assert "'setup_1_6_allowed':False" in module

assert 'import radar_autonomous_learning_41_60_v1 as learning4160' in cloud
assert "'/autonomous-simulator/learning-41-60-v1'" in cloud
assert "'/autonomous-simulator/learning-v3'" in cloud
assert "out['dashboard_contract']='AUTONOMOUS_SIMULATOR_V4'" in cloud
assert "out['automatic_promotion']=False" in cloud
assert "out['automatic_release']=False" in cloud
assert "out['live_execution_allowed']=False" in cloud

version=json.loads((ROOT/'version.json').read_text(encoding='utf-8-sig'))
assert version.get('version')=='1.5.28', version
assert 'exec python cloud_service_v9.py' in (ROOT/'start.sh').read_text(encoding='utf-8')

print(json.dumps({
    'status':'PASS','scope':'AUTONOMOUS_PAPER_PRIORITIES_41_60',
    'stable_windows_version':'1.5.28','setup_built':False,
    'automatic_promotion':False,'automatic_release':False,
    'live_execution_allowed':False,'real_trading':False,
},sort_keys=True))