from pathlib import Path


def test_radar_sync_edge_uses_bounded_concurrency_and_latency_telemetry():
    src=Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    assert 'const WRITE_CONCURRENCY=20;' in src
    assert 'async function mapConcurrent' in src
    assert 'Promise.all(chunk.map(fn))' in src
    assert 'edge_ms:Date.now()-started' in src or 'out.edge_ms=Date.now()-started' in src
    assert 'input_counts' in src


def test_radar_sync_edge_preserves_immutable_portfolio_guards():
    src=Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    assert 'portfolio_values immutable mismatch' in src
    assert 'portfolio_values origin collision' in src
    assert 'portfolio_values duplicate batch mismatch' in src
    assert '.eq("agent_id",row.agent_id).eq("ts",row.ts).maybeSingle()' in src
    assert '.eq("origin_node",row.origin_node).eq("origin_id",String(row.origin_id)).maybeSingle()' in src


def test_radar_sync_event_dedupe_remains_source_url_aware():
    src=Path('supabase/functions/radar-sync/index.ts').read_text(encoding='utf-8')
    assert 'eventSeen=new Set<string>()' in src
    assert '.eq("source",x.source||"unknown").eq("url",x.url).maybeSingle()' in src
    assert 'onConflict:"origin_node,origin_id"' in src
