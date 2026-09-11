from pathlib import Path


def test_radar_sync_replays_restored_portfolio_marks_by_natural_identity():
    source = Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    assert 'const marks=Array.isArray(b.portfolio_values)' in source
    assert 'from("portfolio_values").upsert(rows,{onConflict:"agent_id,ts",ignoreDuplicates:true})' in source


def test_radar_sync_does_not_rekey_same_observed_mark_by_ephemeral_origin_id():
    source = Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    mark_block = source.split('const marks=Array.isArray(b.portfolio_values)', 1)[1].split('const nodes=', 1)[0]
    assert 'onConflict:"origin_node,origin_id"' not in mark_block
    assert 'onConflict:"agent_id,ts"' in mark_block
    assert 'ignoreDuplicates:true' in mark_block


def test_radar_sync_remains_private_token_authenticated():
    source = Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    assert 'x-radar-token' in source.lower()
    assert 'EXPECTED_HASH' in source
    assert 'unauthorized' in source
