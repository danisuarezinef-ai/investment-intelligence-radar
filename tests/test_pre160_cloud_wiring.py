import json
from pathlib import Path


def test_pre160_does_not_publish_an_incremental_windows_release():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert version=='1.5.28'


def test_cloud_exposes_read_only_pre160_and_mobile_contracts():
    source=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    assert "'/pre160-evaluation-v1':200" in source
    assert "'/mobile-summary-v2':200" in source
    assert "if path=='/pre160-evaluation-v1'" in source
    assert "if path=='/mobile-summary-v2'" in source
    assert 'push_pre160_evaluation' in source
    assert "pre160={'status':'DEGRADED_RETRY'" in source
    assert 'REAL_TRADING=False' in source


def test_pre160_authority_failure_is_fail_soft_for_core_paper_checkpoint():
    source=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    checkpoint=source.index('checkpoint=push_engine_checkpoint()')
    pre=source.index('pre160=push_pre160_evaluation()')
    assert checkpoint < pre
    assert 'except Exception as pre_exc' in source
    assert "_PRE160_STATUS={'status':'SYNCED'" in source
