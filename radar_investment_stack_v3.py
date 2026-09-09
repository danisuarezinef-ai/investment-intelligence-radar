"""Read-only integration of Shadow v3, Attribution v3, Learning v3, Model Competition v3 and Multi-Benchmark v1."""
from __future__ import annotations

from radar_attribution_v3 import attribution_summary_v3
from radar_learning_engine_v3 import learn_v3
from radar_model_competition_v3 import compete_models
from radar_multi_benchmark_v1 import compare_benchmarks, benchmark_gate

REAL_TRADING=False


def investment_stack_v3_snapshot(forward_records=None, model_metrics=None, min_learning_samples=20):
    records=list(forward_records or [])
    attribution=attribution_summary_v3(records)
    learning=learn_v3(records,min_samples=min_learning_samples)
    competition=compete_models(model_metrics or [])
    benchmarks=compare_benchmarks(records)
    return {
        'attribution_v3':attribution,
        'learning_v3':learning,
        'model_competition_v3':competition,
        'multi_benchmark_v1':benchmarks,
        'benchmark_gate':benchmark_gate(benchmarks),
        'shadow_portfolio_v3':'ACCOUNT_STATE_API_READY',
        'automatic_application':False,
        'can_trade':False,
        'real_trading':False,
    }
