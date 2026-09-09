"""Cloud service v3 — unified validation and autonomous research runtime."""
import json
import sqlite3
import threading
import time

import cloud_service_v2 as base_v2
from radar_validation_runtime_v3 import validation_runtime_v3
from radar_ops_health_v1 import ops_health
from radar_priority_runtime_v1 import priority_snapshot
from radar_operational_pipeline_v1 import operational_pipeline, market_telemetry
from radar_market_runtime_v2 import provider_telemetry
from radar_fundamentals_point_in_time_v1 import fundamental_coverage
from radar_forward_outcome_sync_v1 import sync_forward_outcomes_once
from radar_continuous_research_v2 import continuous_research_loop
from radar_brain_dashboard_v1 import brain_dashboard

REAL_TRADING=False
BaseHandler=base_v2.ValidationHandler


def priority_runtime_live():
    validation=validation_runtime_v3();health=ops_health(validation);operational=operational_pipeline();fresh=health.get('freshness') or {};gate=validation.get('paper_gate_evidence') or {};shadow=health.get('shadow_portfolio') or {}
    endpoint_status={'/health':'NOT_VERIFIED','/snapshot':'NOT_VERIFIED','/dashboard-v2':'NOT_VERIFIED','/notifications':'NOT_VERIFIED','/pc-sync':'NOT_VERIFIED','/node-heartbeat':'CLIENT_AUTH_REQUIRED_NOT_LIVE_VERIFIED','/validation-v3':200,'/ops-health':200,'/operational-pipeline-v1':200,'/market-telemetry-v1':200,'/provider-telemetry-v1':200,'/fundamentals-v1':200,'/brain-research-v1':200}
    freshness={'market':(fresh.get('market_data') or {}).get('status','NOT_VERIFIED'),'events':(fresh.get('events') or {}).get('status','NOT_VERIFIED'),'predictions':(fresh.get('predictions') or {}).get('status','NOT_VERIFIED'),'cloud_sync':(fresh.get('cloud_sync') or {}).get('status','NOT_VERIFIED'),'forward_outcomes':(fresh.get('forward_outcomes') or {}).get('status','NOT_VERIFIED')}
    promotion_metrics={'days':gate.get('forward_days'),'decisions':gate.get('decisions'),'max_drawdown':gate.get('max_drawdown_pct'),'benchmark_coverage':gate.get('benchmark_coverage'),'cost_coverage':gate.get('cost_coverage'),'positive_months':gate.get('positive_months'),'degradation_clear':gate.get('degradation_clear')}
    account={'equity':None,'cash':None,'invested':shadow.get('approved_budget_total')};paper=validation.get('paper') or {}
    if paper.get('configured'):account={'equity':paper.get('total'),'cash':paper.get('cash'),'invested':paper.get('invested')}
    opportunities=[{'symbol':row.get('symbol'),'score':row.get('score'),'risk':row.get('risk')} for row in operational.get('universe',{}).get('screened',[])[:12]]
    payload=priority_snapshot(account=account,decision=None,opportunities=opportunities,forward_records=operational.get('forward_records') or [],models=[],endpoint_status=endpoint_status,freshness=freshness,promotion_metrics=promotion_metrics)
    payload['operational_pipeline']=operational
    payload['brain']=brain_dashboard(forward_status={'records':len(operational.get('forward_records') or [])},paper_status=paper,cloud_status={'freshness':freshness})
    payload['wiring']={'source':'LIVE_READ_ONLY_OBSERVED_STATE','priority_runtime':'LIVE','forward_capture_engine':'radar_forward_engine','forward_outcome_sync':'LIVE_IDEMPOTENT_MATURE_OUTCOME_RESEND','continuous_research_brain':'LIVE_DAEMON_SIMULATED_RESEARCH_ONLY','brain_research_endpoint':'LIVE_READ_ONLY','priority_forward_records':'LIVE_MATURED_LEDGER_WITH_PROSPECTIVE_BENCHMARK_AND_PAPER_COST_MODEL','priority_model_competition':'LIVE_DERIVED_FROM_MATURE_FORWARD_MODEL_METRICS_FAIL_CLOSED','provider_attempt_telemetry':'LIVE_OBSERVED_ATTEMPTS','provider_circuit_breaker':'LIVE_PERSISTED_STATE','fundamentals':'LIVE_POINT_IN_TIME_SEC_SUPPORTED_ASSETS','global_universe_v3':'LIVE_READ_ONLY_OBSERVED_STATE','valuation_engine_v1':'LIVE_FAIL_CLOSED','portfolio_optimizer_v3':'LIVE_FAIL_CLOSED_MISSING_VERIFIED_EXPECTED_RETURN','paper_authority':'OPERATIONAL_PIPELINE_V1_NO_LEGACY_MOMENTUM_FALLBACK','generic_forward_autonomy_v1':'VERIFIED_CODE_ONLY'}
    payload['can_trade']=False;payload['real_trading']=False;return payload


class ValidationV3Handler(BaseHandler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        try:
            if path=='/ops-health':self._send(200,ops_health(validation_runtime_v3()));return
            if path=='/validation-v3':
                payload=validation_runtime_v3();payload['can_trade']=False;payload['auto_promote']=False;payload['real_trading']=False;self._send(200,payload);return
            if path=='/priority-v1':self._send(200,priority_runtime_live());return
            if path=='/brain-research-v1':self._send(200,brain_dashboard());return
            if path=='/operational-pipeline-v1':self._send(200,operational_pipeline());return
            if path=='/market-telemetry-v1':self._send(200,market_telemetry());return
            if path=='/provider-telemetry-v1':self._send(200,provider_telemetry(24));return
            if path=='/fundamentals-v1':self._send(200,fundamental_coverage());return
        except Exception as exc:
            self._send(500,{'status':'FAILED','error':str(exc)[:800],'can_trade':False,'real_trading':False});return
        super().do_GET()


def _resilient_learning_loop(max_schema_retries=3):
    """Retry only the known concurrent SQLite ADD COLUMN race during startup."""
    retries=0
    while True:
        try:return base_v2.base.learning_loop()
        except sqlite3.OperationalError as exc:
            if 'duplicate column name' not in str(exc).lower() or retries>=max_schema_retries:raise
            retries+=1;print(f'[learning] schema init race detected; retry={retries}',flush=True);time.sleep(.25*retries)


def _forward_outcome_sync_loop(interval_seconds=60):
    """Resend only already-matured immutable outcomes; never creates/backfills decisions."""
    while True:
        try:
            result=sync_forward_outcomes_once(750);print(f'[forward-outcome-sync] sent={result.get("sent",0)} idempotent={result.get("idempotent",False)}',flush=True)
        except Exception as exc:print('[forward-outcome-sync] ERROR '+repr(exc),flush=True)
        time.sleep(max(30,int(interval_seconds)))


# Desktop 1.5.14 sends structured heartbeat detail. SQLite TEXT parameters must
# be normalized before the legacy heartbeat writer sees them.
_original_sync_node_heartbeat=base_v2.base.run_worker.sync_node_heartbeat

def _safe_sync_node_heartbeat(*args, **kwargs):
    detail=kwargs.get('detail')
    if detail is not None and not isinstance(detail,str):
        kwargs['detail']=json.dumps(detail,ensure_ascii=False,sort_keys=True)
    return _original_sync_node_heartbeat(*args,**kwargs)

base_v2.base.run_worker.sync_node_heartbeat=_safe_sync_node_heartbeat
base_v2.base.run_worker._Handler=ValidationV3Handler

if __name__=='__main__':
    base=base_v2.base
    threading.Thread(target=base.supabase_sync_loop,name='supabase-sync',daemon=True).start()
    threading.Thread(target=base.learning_sync_loop,name='learning-sync',daemon=True).start()
    threading.Thread(target=_resilient_learning_loop,name='learning-engine',daemon=True).start()
    threading.Thread(target=_forward_outcome_sync_loop,name='forward-outcome-sync',daemon=True).start()
    threading.Thread(target=continuous_research_loop,name='continuous-research-brain',daemon=True).start()
    base.run_worker.main()
