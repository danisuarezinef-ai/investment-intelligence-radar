from pathlib import Path


def test_edge_exposes_clickable_cockpit_contract_fields():
    edge=Path('supabase/functions/radar-simulator-league/index.ts').read_text(encoding='utf-8')
    for field in ('v_score','v_confidence','v_components','v_trend','readiness','eta_text','eta_days_low','eta_days_high','dynamic_required_days','risk_guard_ok','evidence_ok','quality_ok','confidence_ok'):
        assert field in edge


def test_desktop_explains_score_and_eta_in_spanish():
    ui=Path('radar_simulation_desktop_v3.py').read_text(encoding='utf-8')
    for text in ('Calidad decisión','Rendimiento/riesgo','Control riesgo','Consistencia','Generalización*','Evidencia','Confianza v','Ventaja v','Ventaja equity','Readiness'):
        assert text in ui
    assert 'ETA indeterminada' in ui
    assert 'proxy conservador' in ui
