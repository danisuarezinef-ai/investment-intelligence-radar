import json
from pathlib import Path

import radar_simulation_desktop_v2 as lab


def test_release_is_v1522_or_newer():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int,version.split('.'))) >= (1,5,22)


def test_windows_build_packages_cloud_aware_simulation_lab():
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    assert '--name RadarSimulationLab ' in build
    entrypoints=('radar_simulation_desktop_v2.py','radar_simulation_desktop_v3.py','radar_simulation_desktop_v4.py')
    assert any(name in build for name in entrypoints)
    if 'radar_simulation_desktop_v4.py' in build:
        v4=Path('radar_simulation_desktop_v4.py').read_text(encoding='utf-8')
        assert 'cockpit.VScoreLab' in v4
    elif 'radar_simulation_desktop_v3.py' in build:
        v3=Path('radar_simulation_desktop_v3.py').read_text(encoding='utf-8')
        assert 'legacy.CloudAwareLab' in v3


def test_cloud_autonomy_endpoints_are_wired_into_lab():
    assert lab._CLOUD_ENDPOINTS['simulator']=='/simulator-status-v1'
    assert lab._CLOUD_ENDPOINTS['e2e']=='/autonomy-e2e-v1'
    assert lab._CLOUD_ENDPOINTS['soak']=='/autonomy-soak-v1'
    source=Path('radar_simulation_desktop_v2.py').read_text(encoding='utf-8')
    assert 'recent_runs' in source
    assert 'recent_experiments' in source
    assert 'REAL_TRADING=False' in source


def test_cloud_status_renders_real_autonomy_fields_without_mutating_trading():
    simulator={
        'active':True,'status':'ACTIVE','generation':4,'completed_cycles':36,'completed_experiments':12,
        'paper':{'enabled':True,'total':1012.5},'last_cycle_at':'2026-09-10T16:25:00+00:00',
        'recent_runs':[{'run_id':36,'generation':4,'status':'COMPLETED','paper_status':'OK','research_status':'NOT_DUE','completed_at':'2026-09-10T16:25:00+00:00'}],
        'recent_experiments':[{'experiment_id':'exp-12','generation':3,'stage':'SHADOW_REVIEW','gate_status':'PASS_RESEARCH','research_score':0.42}],
        'real_trading':False,
    }
    text=lab.format_autonomy_status(simulator,{'status':'PASS'},{'status':'COLLECTING_EVIDENCE'})
    assert 'generación 4' in text
    assert 'ciclos 36' in text
    assert 'experimentos 12' in text
    assert 'PAPER ON' in text
    assert 'REAL TRADING OFF' in text
    runs=lab.format_recent_runs(simulator)
    assert runs and 'run 36' in runs[0] and 'gen 4' in runs[0]
    experiments=lab.format_recent_experiments(simulator)
    assert experiments and 'exp-12' in experiments[0] and 'PASS_RESEARCH' in experiments[0]
    assert lab.REAL_TRADING is False
