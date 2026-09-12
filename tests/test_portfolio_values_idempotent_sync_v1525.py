import json
from pathlib import Path

import radar_supabase_sync as sync


def test_release_identity_is_at_least_v1526_and_installer_matches():
    version = json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    installer = Path('installer/Radar.iss').read_text(encoding='utf-8')
    numeric = tuple(int(part) for part in version.split('.'))
    assert numeric >= (1, 5, 26)
    assert f'#define MyAppVersion "{version}"' in installer


def _mark_block():
    source = Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    start = 'const rawMarks=Array.isArray(b.portfolio_values)'
    return source, source.split(start, 1)[1].split('const nodes=', 1)[0]


def test_radar_sync_replays_restored_portfolio_marks_by_natural_identity():
    source, mark_block = _mark_block()
    assert 'eq("agent_id",row.agent_id).eq("ts",row.ts).maybeSingle()' in mark_block
    assert 'portfolio_values immutable mismatch' in mark_block
    assert 'portfolio_values duplicate batch mismatch' in mark_block
    assert 'sameNumeric(existing.equity,row.equity)' in mark_block
    assert 'sameNumeric(existing.drawdown,row.drawdown,1e-9)' in mark_block
    assert 'tolerance=1e-6' in source


def test_radar_sync_checks_provenance_identity_without_weakening_unique_indexes():
    _, mark_block = _mark_block()
    assert 'eq("origin_node",row.origin_node).eq("origin_id",String(row.origin_id)).maybeSingle()' in mark_block
    assert 'portfolio_values origin collision' in mark_block
    assert 'from("portfolio_values").insert(row)' in mark_block
    assert 'WRITE_CONCURRENCY=20' in Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')


def test_origin_ids_cross_json_as_exact_decimal_strings(monkeypatch):
    monkeypatch.setattr(sync, '_SYNC_PREFIX', 0x7FFFFFFF)
    first = sync._origin_id(1)
    second = sync._origin_id(2)
    assert isinstance(first, str) and isinstance(second, str)
    assert int(first) > 2**53
    assert int(second) - int(first) == 1
    assert json.loads(json.dumps({'origin_id': first}))['origin_id'] == first
    assert int(second) < 2**63


def test_radar_sync_remains_private_token_authenticated():
    source = Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    assert 'x-radar-token' in source.lower()
    assert 'EXPECTED_HASH' in source
    assert 'unauthorized' in source
