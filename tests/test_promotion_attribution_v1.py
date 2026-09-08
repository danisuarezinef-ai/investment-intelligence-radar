import unittest
from radar_promotion_attribution_v1 import promotion_gate,confidence_calibration,performance_attribution,degradation_check

class PromotionAttributionTests(unittest.TestCase):
    def strong(self):
        return {'forward_days':120,'matured_predictions':150,'decisions':80,'max_drawdown_pct':-6,
                'brier':.16,'hit_rate':.58,'excess_return_pct':4.0,'positive_months':4,
                'ledger_integrity':True,'pit_verified':True,'costs_included':True}
    def test_gate_can_only_mark_review_ready(self):
        r=promotion_gate(self.strong());self.assertTrue(r['ready_for_live_review']);self.assertFalse(r['can_trade']);self.assertFalse(r['auto_promote']);self.assertFalse(r['real_trading'])
    def test_missing_evidence_fails_closed(self):
        r=promotion_gate({});self.assertFalse(r['ready_for_live_review']);self.assertTrue(r['failed'])
    def test_bad_drawdown_blocks(self):
        e=self.strong();e['max_drawdown_pct']=-18;r=promotion_gate(e);self.assertIn('drawdown',r['failed'])
    def test_calibration(self):
        r=confidence_calibration([{'confidence':.8,'hit':True},{'confidence':.2,'hit':False}]);self.assertEqual(r['n'],2);self.assertAlmostEqual(r['brier'],.04)
    def test_string_false_is_not_truthy_hit(self):
        r=confidence_calibration([{'confidence':.2,'hit':'false'},{'confidence':.8,'hit':'true'}]);self.assertEqual(r['n'],2);self.assertAlmostEqual(r['hit_rate'],.5);self.assertAlmostEqual(r['brier'],.04)
    def test_invalid_hit_is_excluded(self):
        r=confidence_calibration([{'confidence':.5,'hit':'unknown'}]);self.assertEqual(r['n'],0);self.assertEqual(r['invalid'],1);self.assertIsNone(r['brier'])
    def test_attribution_preserves_unexplained(self):
        r=performance_attribution([{'portfolio_return':3,'benchmark_return':2,'selection':1.2,'costs':-.2}]);self.assertAlmostEqual(r['excess_return'],1);self.assertAlmostEqual(r['unexplained'],2);self.assertEqual(r['return_linking'],'geometric')
    def test_attribution_compounds_multiple_periods(self):
        r=performance_attribution([{'portfolio_return':10,'benchmark_return':5},{'portfolio_return':-10,'benchmark_return':-5}]);self.assertAlmostEqual(r['portfolio_return'],-1.0);self.assertAlmostEqual(r['benchmark_return'],-.25);self.assertAlmostEqual(r['excess_return'],-.75)
    def test_attribution_missing_return_is_not_zero(self):
        r=performance_attribution([{'portfolio_return':3,'benchmark_return':2},{'benchmark_return':1}]);self.assertIsNone(r['portfolio_return']);self.assertIsNone(r['excess_return']);self.assertEqual(r['missing_portfolio_returns'],1)
    def test_degradation_detected(self):
        r=degradation_check({'hit_rate':.62,'brier':.14},{'hit_rate':.50,'brier':.22});self.assertTrue(r['degraded']);self.assertFalse(r['automatic_model_retirement'])
    def test_degradation_missing_metrics_is_incomplete_not_zero(self):
        r=degradation_check({'hit_rate':.62},{'hit_rate':.50});self.assertTrue(r['degraded']);self.assertFalse(r['evidence_complete']);self.assertIsNone(r['deltas']['brier_increase']);self.assertIn('brier_increase',r['missing_metrics'])
    def test_no_comparable_degradation_metrics_returns_unknown(self):
        r=degradation_check({},{});self.assertIsNone(r['degraded']);self.assertFalse(r['evidence_complete'])

if __name__=='__main__':unittest.main()
