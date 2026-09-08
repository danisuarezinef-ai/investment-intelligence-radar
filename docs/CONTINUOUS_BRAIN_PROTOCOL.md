# Continuous Brain Protocol

## Objective
Radar should become better as time passes without learning itself into overfit, leakage or catastrophic forgetting.

## Two learning clocks
1. **Fast historical clock**: generates hypotheses, challenger families, ablations and search priors. It cannot promote an operational champion.
2. **Slow live-forward clock**: immutable predictions mature into genuine evidence. Only this clock can authorize operational promotion.

## Improvement loop
`collect PIT evidence -> freeze prediction -> mature outcome -> score by horizon/regime -> attribute errors -> compare champion/challengers/baselines -> update transfer evidence -> propose next generation -> shadow -> live promotion gate`

## Memory
The brain must preserve model version, parent, feature/thesis fingerprints, data cutoff, prediction hash, mature outcome, regime, calibration, risk, attribution and failure patterns. Negative results remain first-class evidence.

## Anti-forgetting
A candidate must not improve one recent regime by destroying older validated capabilities. Promotion therefore evaluates live objective, calibration and drawdown; later versions should add per-regime regression gates once sample sizes permit.

## Meta-learning
Learner families earn future experiment budget when historical success repeatedly transfers to live success. Historical-to-live disagreement reduces that transfer weight. This changes *what Radar experiments with*, not the truth of past outcomes.

## Complexity budget
New components compete against simple baselines and ablations. Complexity that repeatedly adds no mature live value is retired rather than accumulated indefinitely.

## Safety
- `REAL_TRADING=false`.
- Historical-only success cannot promote.
- No backfilled prediction may be labelled forward.
- Final/deep vault evidence is qualification evidence, not training data.
- Software tests do not imply investment performance.
