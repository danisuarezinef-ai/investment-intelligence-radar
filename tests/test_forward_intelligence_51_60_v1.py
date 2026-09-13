from datetime import datetime,timezone,timedelta
import radar_forward_intelligence_51_60_v1 as h

def rows(n=40,regime='risk_on_growth',horizon='1d'):
    t=datetime(2026,9,1,tzinfo=timezone.utc);out=[]
    for i in range(n):
        out.append({'prediction_id':str(i),'created_at':(t+timedelta(hours=i)).isoformat(),'evaluated_at':(t+timedelta(hours=i+24)).isoformat(),
          'horizon':horizon,'confidence':.7,'uncertainty':{'regime':regime},'decision_state':'BUY','matured':True,'natural':True,
          'net_return':.01 if i%2==0 else -.005,'quality_checks':{'pit_valid':True,'backfilled':False},'real_trading':False})
    return out

def test_51_authority_passes_only_pit_forward():
    x=h.evidence_authority(rows());assert x['status']=='PASS';assert x['single_authority']=='decision_forward_ledger';assert x['real_trading'] is False

def test_52_60_are_fail_closed_and_no_live_authority():
    b=h.board(rows(60));assert set(b['tasks'])=={str(i) for i in range(51,61)}
    assert b['automatic_promotion'] is False and b['live_execution_allowed'] is False and b['real_trading'] is False
    assert b['tasks']['55']['evidence']['can_only_reduce_confidence'] is True
    assert b['tasks']['59']['evidence']['cannot_accelerate_forward_maturity'] is True

def test_unknown_regime_abstains():
    r=rows(30,regime='UNKNOWN');x=h.unknown_regime_mode(r);assert x['status']=='ABSTAIN_UNKNOWN_REGIME';assert x['new_risk_allowed'] is False

def test_horizon_calibration_does_not_fake_long_horizons():
    x=h.calibration_by_horizon(rows(40,horizon='1d'));assert x['status']=='PASS_1D_ONLY';assert x['matured_horizons']==['1d']

def test_half_life_weights_without_backfill_credit():
    x=h.evidence_half_life(rows(20),now=datetime(2026,9,20,tzinfo=timezone.utc));assert x['status']=='PASS';assert x['backfill_creates_no_age_credit'] is True
