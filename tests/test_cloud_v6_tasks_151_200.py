from pathlib import Path


def test_cloud_v6_composes_v5_and_preserves_safety_boundary():
    src = Path('cloud_service_v6.py').read_text(encoding='utf-8')
    assert 'import cloud_service_v5 as base5' in src
    assert 'base5.start_runtime()' in src
    assert 'REAL_TRADING = False' in src
    for endpoint in (
        '/pre160-audit-151-200-v1', '/pre160-slo-v1', '/pre160-data-integrity-v1',
        '/pre160-evidence-maturity-v3', '/pre160-governance-v3', '/pre160-recovery-v2',
        '/pre160-release-authority-v2',
    ):
        assert endpoint in src
    assert "'setup_allowed': False" in src
    assert "'automatic_release': False" in src
    assert "'automatic_promotion': False" in src
    assert "'automatic_demotion': False" in src
    assert "'real_trading': False" in src


def test_start_script_points_to_v6_without_windows_release_change():
    start = Path('start.sh').read_text(encoding='utf-8')
    assert 'cloud_service_v6.py' in start
    assert 'cloud_service_v5.py' not in start
    version = __import__('json').loads(Path('version.json').read_text(encoding='utf-8-sig'))['version']
    assert version == '1.5.28'


def test_task_spec_defines_full_151_200_scope_and_invariants():
    spec = Path('PRE160_TASKS_151_200.md').read_text(encoding='utf-8')
    for task in range(151, 201):
        assert f'|{task}|' in spec
    assert 'REAL_TRADING=false' in spec
    assert '1.5.28' in spec
    assert 'PENDING_SAMPLE' in spec
    assert 'PENDING_TIME' in spec
    assert 'No synthetic trade' in spec
