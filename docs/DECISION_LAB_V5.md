# Decision Lab v5

Status: implementation candidate. REAL_TRADING=false.

Decision Lab v5 normalizes comparable investment decisions into `BUY`, `WATCH`, `HOLD`, `REDUCE`, and `AVOID` cards. Every card carries horizon, model score, confidence, empirical expected return when available, empirical upside/downside, valuation risk, comparison with the best available alternative, evidence completeness, blockers, and an explanation.

## Fail-closed rules

New capital cannot receive `BUY` when critical evidence is missing. The current prediction store does not contain a verified valuation-risk field or explicit per-decision cost evidence, so runtime cards remain `WATCH` for non-holdings unless those inputs are genuinely connected. Existing holdings can be marked `REDUCE` when evidence is incomplete and the model score is materially negative.

At least five matured same-symbol/same-horizon outcomes are required before empirical return distribution is considered available. This is a governance minimum, not a claim of statistical sufficiency or optimality.

## Runtime integration

`radar_validation_runtime_v2.validation_runtime_snapshot()` includes `decision_lab_v5` alongside shadow evidence, Promotion Gate, Forward Evidence health, and Historical Lab status.

## Safety invariants

- No synthetic valuation evidence.
- No assumed transaction cost.
- Missing evidence stays missing.
- `can_trade=false`.
- `REAL_TRADING=false`.
