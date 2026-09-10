import json
from pathlib import Path

import radar_persistent_authority_v1 as authority
import radar_simulation_desktop_v2 as lab


def test_release_is_v1523_or_newer():
    version=json.loads(Path('version.json').read_text(encoding='utf-8'))['version']
    assert tuple(map(int,version.split('.'))) >= (1,5,23)


def test_daily_equity_summary_uses_only_observed_rows_without_backfill():
    rows=[
        {'day':'2026-09-07','equity':'1000.00','agents':5},
        {'day':'2026-09-08','equity':'1010.00','agents':5},
        {'day':'2026-09-09','equity':'995.00','agents':5},
        {'day':'2026-09-10','equity':'1020.00','agents':5},
    ]
    out=authority.summarize_paper_equity_daily(rows,30)
    assert out['observed_days']==4
    assert [r['date'] for r in out['daily_equity_30d']]==['2026-09-07','2026-09-08','2026-09-09','2026-09-10']
    assert out['current_equity']==1020.0
    assert round(out['month_change_pct'],6)==2.0
    assert out['month_high']==1020.0
    assert out['month_low']==995.0
    assert out['backfilled'] is False
    assert out['reconstructed'] is False
    assert out['real_trading'] is False


def test_equity_chart_geometry_preserves_up_and_down_sequence():
    series=[
        {'date':'2026-09-07','equity':1000},
        {'date':'2026-09-08','equity':1010},
        {'date':'2026-09-09','equity':995},
        {'date':'2026-09-10','equity':1020},
    ]
    pts=lab.equity_chart_points(series,600,175)
    assert len(pts)==4
    assert pts[1]['y'] < pts[0]['y']
    assert pts[2]['y'] > pts[1]['y']
    assert pts[3]['y'] < pts[2]['y']
    assert pts[0]['date']=='2026-09-07' and pts[-1]['date']=='2026-09-10'


def test_cloud_and_edge_sources_expose_durable_equity_endpoint():
    cloud=Path('cloud_service_v3.py').read_text(encoding='utf-8')
    edge=Path('supabase/functions/radar-learning-sync/index.ts').read_text(encoding='utf-8')
    migration=Path('supabase/migrations/20260910171500_paper_equity_daily_chart.sql').read_text(encoding='utf-8')
    assert "'/simulator-equity-v1'" in cloud
    assert 'paper_equity_curve(30)' in cloud
    assert 'paper_equity_daily' in edge
    assert 'radar_paper_equity_daily' in edge
    assert 'row_number() over' in migration.lower()
    assert 'd.agents = e.n' in migration
    assert 'backfill' in migration.lower()


def test_lab_renders_native_canvas_chart_and_fetches_equity():
    source=Path('radar_simulation_desktop_v2.py').read_text(encoding='utf-8')
    assert lab._CLOUD_ENDPOINTS['equity']=='/simulator-equity-v1'
    assert 'Canvas' in source
    assert 'EVOLUCIÓN PAPER · ÚLTIMOS 30 DÍAS' in source
    assert 'base.GREEN if rising else base.RED' in source
    assert 'month_change_pct' in source
    assert 'month_high' in source and 'month_low' in source
    assert 'sin backfill' in source
    assert lab.REAL_TRADING is False


def test_chart_summary_reports_partial_real_history_transparently():
    text=lab.equity_summary_text({'observed_days':4,'window_days':30})
    assert '4 días observados' in text
    assert 'ventana 30d' in text
    assert 'sin backfill' in text
