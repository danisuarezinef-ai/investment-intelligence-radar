"""Cloud service v3 — read-only unified validation runtime endpoint."""
import threading

import cloud_service_v2 as base_v2
from radar_validation_runtime_v3 import validation_runtime_v3
from radar_ops_health_v1 import ops_health
from radar_priority_runtime_v1 import priority_snapshot
from radar_operational_pipeline_v1 import operational_pipeline, market_telemetry

REAL_TRADING=False
BaseHandler=base_v2.ValidationHandler


def priority_runtime_live():
    """Execute the v6 read-only priority surface from observed runtime state only."""
    validation=validation_runtime_v3()
    health=ops_health(validation)
    operational=operational_pipeline()
    fresh=health.get('freshness') or {}
    gate=validation.get('paper_gate_evidence') or {}
    shadow=health.get('shadow_portfolio') or {}
    endpoint_status={
        '/health':'NOT_VERIFIED','/snapshot':'NOT_VERIFIED','/dashboard-v2':'NOT_VERIFIED',
        '/notifications':'NOT_VERIFIED','/pc-sync':'NOT_VERIFIED','/node-heartbeat':'NOT_VERIFIED',
        '/validation-v3':200,'/ops-health':200,'/operational-pipeline-v1':200,'/market-telemetry-v1':200,
    }
    freshness={
        'market':(fresh.get('market_data') or {}).get('status','NOT_VERIFIED'),
        'events':(fresh.get('events') or {}).get('status','NOT_VERIFIED'),
        'predictions':(fresh.get('predictions') or {}).get('status','NOT_VERIFIED'),
        'cloud_sync':(fresh.get('cloud_sync') or {}).get('status','NOT_VERIFIED'),
        'forward_outcomes':(fresh.get('forward_outcomes') or {}).get('status','NOT_VERIFIED'),
    }
    promotion_metrics={
        'days':gate.get('forward_days'),'decisions':gate.get('decisions'),
        'max_drawdown':gate.get('max_drawdown_pct'),'benchmark_coverage':gate.get('benchmark_coverage'),
        'cost_coverage':gate.get('cost_coverage'),'positive_months':gate.get('positive_months'),
        'degradation_clear':gate.get('degradation_clear'),
    }
    account={'equity':None,'cash':None,'invested':shadow.get('approved_budget_total')}
    paper=validation.get('paper') or {}
    if paper.get('configured'):
        account={'equity':paper.get('total'),'cash':paper.get('cash'),'invested':paper.get('invested')}
    opportunities=[]
    for row in operational.get('universe',{}).get('screened',[])[:12]:
        opportunities.append({'symbol':row.get('symbol'),'score':row.get('score'),'risk':row.get('risk')})
    payload=priority_snapshot(
        account=account,decision=None,opportunities=opportunities,
        forward_records=operational.get('forward_records') or [],models=[],endpoint_status=endpoint_status,
        freshness=freshness,promotion_metrics=promotion_metrics)
    payload['operational_pipeline']=operational
    payload['wiring']={
        'source':'LIVE_READ_ONLY_OBSERVED_STATE',
        'priority_runtime':'LIVE',
        'forward_capture_engine':'radar_forward_engine',
        'priority_forward_records':'LIVE_MATURED_LEDGER_ONLY_FAIL_CLOSED_ON_MISSING_BENCHMARK_OR_COST',
        'priority_model_competition':'NOT_WIRED_TO_FORWARD_MODEL_METRICS',
        'global_universe_v3':'LIVE_READ_ONLY_OBSERVED_STATE',
        'valuation_engine_v1':'LIVE_FAIL_CLOSED_MISSING_FUNDAMENTALS',
        'portfolio_optimizer_v3':'LIVE_FAIL_CLOSED_EVIDENCE_GATED',
        'generic_forward_autonomy_v1':'VERIFIED_CODE_ONLY',
    }
    payload['can_trade']=False; payload['real_trading']=False
    return payload


class ValidationV3Handler(BaseHandler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/ops-health':
            try:self._send(200,ops_health(validation_runtime_v3()))
            except Exception as exc:self._send(500,{'status':'FAILED','error':str(exc)[:800],'can_trade':False,'real_trading':False})
            return
        if path=='/validation-v3':
            try:
                payload=validation_runtime_v3()
                payload['can_trade']=False
                payload['auto_promote']=False
                payload['real_trading']=False
                self._send(200,payload)
            except Exception as exc:
                self._send(500,{'ok':False,'error':str(exc)[:800],'can_trade':False,
                                'auto_promote':False,'real_trading':False})
            return
        if path=='/priority-v1':
            try:self._send(200,priority_runtime_live())
            except Exception as exc:self._send(500,{'status':'FAILED','error':str(exc)[:800],
                                                   'can_trade':False,'real_trading':False})
            return
        if path=='/operational-pipeline-v1':
            try:self._send(200,operational_pipeline())
            except Exception as exc:self._send(500,{'status':'FAILED','error':str(exc)[:800],
                                                   'can_trade':False,'real_trading':False})
            return
        if path=='/market-telemetry-v1':
            try:self._send(200,market_telemetry())
            except Exception as exc:self._send(500,{'status':'FAILED','error':str(exc)[:800],
                                                   'can_trade':False,'real_trading':False})
            return
        super().do_GET()


base_v2.base.run_worker._Handler=ValidationV3Handler


if __name__=='__main__':
    base=base_v2.base
    threading.Thread(target=base.supabase_sync_loop,name='supabase-sync',daemon=True).start()
    threading.Thread(target=base.learning_sync_loop,name='learning-sync',daemon=True).start()
    threading.Thread(target=base.learning_loop,name='learning-engine',daemon=True).start()
    base.run_worker.main()
