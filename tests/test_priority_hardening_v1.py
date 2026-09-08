import unittest
from radar_risk_engine_v1 import portfolio_risk_gate,adaptive_risk_multiplier

class RiskEngineTests(unittest.TestCase):
    def status(self,**kw):
        x={'total':200.0,'cash':200.0,'invested':0.0,'positions':[],'max_drawdown_pct':0.0};x.update(kw);return x
    def decision(self,**kw):
        x={'action':'PAPER_BUY_CANDIDATE','confidence':.80,'allocation_fraction':.20};x.update(kw);return x
    def test_hard_drawdown_blocks_new_risk(self):
        r=portfolio_risk_gate(self.status(max_drawdown_pct=-13),self.decision());self.assertTrue(r['blocked']);self.assertEqual(r['allowed_budget'],0);self.assertIn('drawdown_hard_stop',r['reasons'])
    def test_low_confidence_blocks(self):
        r=portfolio_risk_gate(self.status(),self.decision(confidence=.30));self.assertTrue(r['blocked']);self.assertIn('confidence_below_floor',r['reasons'])
    def test_position_cap(self):
        r=portfolio_risk_gate(self.status(),self.decision());self.assertLessEqual(r['allowed_budget'],40.0)
    def test_drawdown_reduces_multiplier(self):
        self.assertLess(adaptive_risk_multiplier(.8,-8),adaptive_risk_multiplier(.8,0))
    def test_never_real_trading(self):
        self.assertFalse(portfolio_risk_gate(self.status(),self.decision())['real_trading'])

if __name__=='__main__':unittest.main()
