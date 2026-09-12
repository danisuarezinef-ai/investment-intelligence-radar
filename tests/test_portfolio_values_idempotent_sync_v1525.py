import json
from pathlib import Path

import radar_supabase_sync as sync


def test_release_identity_is_at_least_v1526_and_installer_matches():
    version = json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    installer = Path('installer/Radar.iss').read_text(encoding='utf-8')
    numeric = tuple(int(part) for part in version.split('.'))
    assert numeric >= (1, 5, 26)
    assert f'#define MyAppVersion "{version}"' in installer


def _source():
    return Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')


def test_radar_sync_replays_restored_portfolio_marks_by_bulk_natural_identity():
    source = _source()
    assert 'async function reconcilePortfolioMarks' in source
    assert '.eq("agent_id",job.agent).in("ts",job.times)' in source
    assert 'portfolio_values immutable mismatch' in source
    assert 'portfolio_values duplicate batch mismatch' in source
    assert 'sameNumeric(existing.equity,row.equity)' in source
    assert 'sameNumeric(existing.drawdown,row.drawdown,1e-9)' in source
    assert 'tolerance=1e-6' in source
    assert 'natural_query_batches' in source


def test_radar_sync_checks_bulk_provenance_identity_without_weakening_unique_indexes():
    source = _source()
    assert '.eq("origin_node",job.node).in("origin_id",job.ids)' in source
    assert 'portfolio_values origin collision' in source
    assert 'bulkInsert("portfolio_values",fresh)' in source
    assert 'const WRITE_CONCURRENCY=20;' in source
    assert 'const READ_CHUNK=100;' in source
    assert 'const WRITE_CHUNK=100;' in source


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
    source = _source()
    assert 'x-radar-token' in source.lower()
    assert 'EXPECTED_HASH' in source
    assert 'unauthorized' in source
