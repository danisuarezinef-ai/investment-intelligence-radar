# Simulation League v-score cockpit — v1.5.25

## Purpose

Turn the PAPER simulator into a simple, visual, auditable competition between one Champion and multiple risk-labelled Challengers.

## Observable outputs

Each competitor exposes: normalized capital on a comparable 1,000-euro base, risk label, 30-day red/green equity path, Aciertos (equity-up days), Errores (equity-down days), drawdown, invested percentage, v-score, v-score confidence, v-score components, promotion readiness and dynamic ETA.

## v-score

Scale: 0..400; neutral 200.

Weighted components:
- decision quality: 30%
- risk-adjusted return: 22%
- risk control: 18%
- consistency: 12%
- generalization/breadth proxy: 10%
- evidence: 8%

Low evidence contracts the score toward v200. Generalization remains explicitly marked as a conservative proxy until regime-linked per-strategy evidence exists.

## Dynamic promotion

There is no fixed 10-day promotion rule. A Challenger must simultaneously satisfy dynamic evidence, v advantage, equity advantage, risk compatibility, confidence and a promotion-readiness threshold. The required evidence horizon varies with advantage magnitude and uncertainty. ETA is derived from the observed readiness trend when possible; otherwise the UI reports that evidence is insufficient or a blocking condition exists.

Promotion changes only the Simulation League role. It does not promote a production model and grants no execution authority.

## Durable PAPER engine

The operational PAPER state is checkpointed exactly: accounts, cash, positions, average prices, trades and marks for all Challengers and the Champion. The checkpoint is hashed and restored before workers start after an ephemeral Railway redeploy. Corrupt checkpoints fail closed.

## Safety

REAL_TRADING=false.
automatic_model_promotion=false.
live_execution_allowed=false.
can_trade=false.
