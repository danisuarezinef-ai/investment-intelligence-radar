import json
import urllib.error
from pathlib import Path

import radar_pc_sync_hook as sync
import radar_promotion_governance_v2 as promotion
import radar_paper_authority_v2 as paper_authority
import radar_forward_ledger_audit_v1 as forward_audit


def test_task_11_windows_cloud_contract_includes_required_endpoints():
    source=Path('radar_pc_sync_hook.py').read_text(encoding='utf-8')
    for endpoint in ('/health','/snapshot','/dashboard-v2','/notifications','/pc-sync','/node-heartbeat','/validation-v3'):
        assert endpoint in source
    assert "'validation_v3':validation.get('payload')" in source
    assert "'validation-v3':validation['ok']" in source


def test_task_11_optional_404_enters_backoff(monkeypatch):
    sync._OPTIONAL_BLOCKED_UNTIL.clear()
    calls={'n':0}
    def missing(path,timeout=20):
        calls['n']+=1
        raise urllib.error.HTTPError('https://example.invalid'+path,404,'Not Found',{},None)
    monkeypatch.setattr(sync,'_get',missing)
    first=sync._get_optional('/validation-v3')
    second=sync._get_optional('/validation-v3')
    assert first['status']=='HTTP_404_BACKOFF' and first['http_status']==404
    assert second['status']=='BACKOFF_404'
    assert calls['n']==1


def test_task_12_version_identity_and_legacy_binary_compatibility():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    installer=Path('installer/Radar.iss').read_text(encoding='utf-8')
    build=Path('build_windows.ps1').read_text(encoding='utf-8')
    assert version=='1.5.21'
    assert '#define MyAppName "Radar de Inversión"' in installer
    assert '#define MyAppVersion "1.5.21"' in installer
    assert '#define MyAppExeName "InvestmentIntelligenceRadar.exe"' in installer
    assert 'OutputBaseFilename=Radar_de_Inversion_Setup' in installer
    assert "PC_SYNC_VERSION='$version'" in build
    assert "APP_VERSION='$version'" in build


def test_task_13_release_gates_cover_full_suite_and_windows_outputs():
    workflow=Path('.github/workflows/windows-release.yml').read_text(encoding='utf-8')
    integration=Path('.github/workflows/integration-ci.yml').read_text(encoding='utf-8')
    assert 'pytest' in integration.lower()
    for phrase in ('Test core','Build application, updater and Setup.exe','Smoke launch Simulation Lab','Verify outputs','Upload Windows installer','Upload update package','Publish stable update channel'):
        assert phrase in workflow


def test_task_15_real_trading_remains_impossible_from_governed_paths():
    assert promotion.REAL_TRADING is False
    assert paper_authority.REAL_TRADING is False
    assert forward_audit.REAL_TRADING is False
    gate=promotion.promotion_governance({},human_approved=True)
    assert gate['live_execution_allowed'] is False
    assert gate['auto_promote'] is False
    assert gate['can_trade'] is False
    assert gate['real_trading'] is False
