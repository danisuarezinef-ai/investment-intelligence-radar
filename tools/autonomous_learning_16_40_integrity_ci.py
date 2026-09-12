from pathlib import Path
import json

root=Path(__file__).resolve().parents[1]
assert json.loads((root/'version.json').read_text(encoding='utf-8-sig'))['version']=='1.5.28'
assert 'exec python cloud_service_v9.py' in (root/'start.sh').read_text(encoding='utf-8')
cloud=(root/'cloud_service_v9.py').read_text(encoding='utf-8')
learning=(root/'radar_autonomous_learning_16_40_v1.py').read_text(encoding='utf-8')
simulator=(root/'radar_autonomous_simulator_v1.py').read_text(encoding='utf-8')
assert 'import radar_autonomous_learning_16_40_v1 as learning1640' in cloud
assert "/autonomous-simulator/learning-v2" in cloud
assert "'dashboard_contract':'AUTONOMOUS_SIMULATOR_V2'" in cloud
assert 'REAL_TRADING=False' in learning
assert "'automatic_promotion':False" in learning
assert "'live_execution_allowed':False" in learning
assert "'acceleration_allowed':False" in learning and "'backfill_allowed':False" in learning
assert 'SIMULATION ONLY — NO REAL MONEY' in learning
assert 'REAL_TRADING=False' in simulator
assert "'automatic_live_promotion':False" in simulator
assert 'paper_step' in (root/'radar_simulator_engine_v3.py').read_text(encoding='utf-8')
print('AUTONOMOUS_LEARNING_16_40_INTEGRITY=PASS')
