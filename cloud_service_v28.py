"""Runtime v28: v27 plus first PAPER trial E-H contracts. REAL_TRADING OFF."""
from __future__ import annotations
import os
import cloud_service_v27 as base27
import radar_first_paper_trial_v1 as trial

REAL_TRADING=False


def readiness():
    return {"runtime":"v28","trial_id":trial.TRIAL_ID,"universe":list(trial.FROZEN_UNIVERSE),
            "agents":list(trial.AGENTS),"learning":trial.learning_contract(),
            "market_data_test_set":"NOT_VERIFIED_UNTIL_OBSERVED_QUOTES_PASS_GATE",
            "end_to_end_pipeline":"NOT_VERIFIED_UNTIL_OBSERVED_DECISION_ORDER_FILL_POSITION",
            "first_paper_trial":"NOT_STARTED","paper_only":True,"broker_submit_enabled":False,"real_trading":False}


class ValidationV28Handler(base27.ValidationV27Handler):
    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path=="/first-paper-trial/readiness-v1":
            self._send(200,readiness()); return
        if path=="/first-paper-trial/manifest-v1":
            sha=(os.getenv("RAILWAY_GIT_COMMIT_SHA") or os.getenv("RADAR_DEPLOY_REV") or "NOT_VERIFIED")
            self._send(200,trial.trial_manifest(git_sha=sha,initial_capital=100000.0,
                risk_rules={"max_position_pct":10,"max_portfolio_exposure_pct":80,"paper_only":True})); return
        super().do_GET()


def main():
    # v27 owns the development worker set and Block-D startup validation.
    base27._patch_development_runtime()
    base27._start_core_threads()
    base27._run_block_d_once()
    import threading
    from http.server import ThreadingHTTPServer
    port=int(os.environ.get("PORT") or 0)
    if port<=0:
        import time
        while True: time.sleep(60)
    ThreadingHTTPServer(("0.0.0.0",port),ValidationV28Handler).serve_forever()

if __name__=="__main__": main()
