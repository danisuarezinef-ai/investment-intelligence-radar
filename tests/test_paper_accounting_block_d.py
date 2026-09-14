import unittest
from radar_paper_accounting_v1 import new_account, apply_fill, mark_to_market, accounting_invariants, block_d_probes


class PaperAccountingBlockDTests(unittest.TestCase):
    def test_buy_sell_and_equity_identity(self):
        s=new_account(10000)
        s,r=apply_fill(s,fill_id='a',order_id='oa',symbol='AAA',side='BUY',qty=10,price=100,fee=1)
        self.assertEqual(r['status'],'APPLIED')
        s,r=apply_fill(s,fill_id='b',order_id='ob',symbol='AAA',side='SELL',qty=4,price=110,fee=1)
        self.assertEqual(r['status'],'APPLIED')
        m=mark_to_market(s,{'AAA':105})
        self.assertAlmostEqual(m['equity'],m['cash']+m['market_value'],places=10)
        self.assertAlmostEqual(m['realized_pnl'],39.0,places=10)
        self.assertEqual(accounting_invariants(s,{'AAA':105})['status'],'PASS')

    def test_duplicate_fill_is_idempotent(self):
        s=new_account(10000)
        s,r=apply_fill(s,fill_id='dup',order_id='o',symbol='AAA',side='BUY',qty=1,price=100,fee=1)
        snapshot=repr(s)
        s,r=apply_fill(s,fill_id='dup',order_id='o',symbol='AAA',side='BUY',qty=1,price=100,fee=1)
        self.assertEqual(r['status'],'DUPLICATE_IGNORED')
        self.assertEqual(repr(s),snapshot)

    def test_fill_id_collision_rejected(self):
        s=new_account(10000)
        s,_=apply_fill(s,fill_id='same',order_id='o1',symbol='AAA',side='BUY',qty=1,price=100,fee=0)
        s2,r=apply_fill(s,fill_id='same',order_id='o2',symbol='AAA',side='BUY',qty=2,price=100,fee=0)
        self.assertEqual(r['status'],'REJECTED')
        self.assertEqual(s2,s)

    def test_insufficient_cash_and_oversell_fail_closed(self):
        s=new_account(100)
        s2,r=apply_fill(s,fill_id='cash',order_id='o1',symbol='AAA',side='BUY',qty=2,price=100,fee=1)
        self.assertEqual(r['reason'],'insufficient_cash'); self.assertEqual(s2,s)
        s=new_account(10000)
        s,_=apply_fill(s,fill_id='buy',order_id='o2',symbol='AAA',side='BUY',qty=1,price=100,fee=0)
        s2,r=apply_fill(s,fill_id='sell',order_id='o3',symbol='AAA',side='SELL',qty=2,price=100,fee=0)
        self.assertEqual(r['reason'],'insufficient_position'); self.assertEqual(s2,s)

    def test_block_d_probe(self):
        self.assertEqual(block_d_probes()['status'],'PASS')


if __name__=='__main__': unittest.main()
