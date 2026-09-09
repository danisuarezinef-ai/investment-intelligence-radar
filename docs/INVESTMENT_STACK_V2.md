# Investment Stack v2

Implements the next five priorities without enabling real trading:

1. Risk Engine v2.1: explicit annualized-volatility evidence and regime risk multipliers, fail-closed when missing.
2. Allocation Engine v2: global capital competition with cash as an explicit alternative and bounded deployment.
3. Global Opportunity Universe v2: progressive cheap-screen -> deep-review -> Decision Lab funnel over caller-supplied candidates.
4. Per-asset Evidence Engine v1: market/fundamentals/news/risk/regime aggregation with freshness, conflicts and completeness.
5. Decision Lab v6: alternative comparison, opportunity-cost utility and recommended budget linkage.

All thresholds are policy defaults unless otherwise evidenced. They are NOT empirically validated as optimal. All modules expose `REAL_TRADING=False` and no broker order path is added.
