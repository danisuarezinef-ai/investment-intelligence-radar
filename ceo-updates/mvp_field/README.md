# MVP_FIELD / FIRST_REAL_GOAL

Purpose: prove one real end-to-end delivery before any further CEO expansion.

This branch is intentionally isolated from the normal Windows/Android development line.
It does **not** publish or install an update and it must not be merged into a release
until the physical field goal passes.

## Frozen scope

Only the happy path is in scope:

1. One AI provider: Gemini.
2. A deterministic decomposer with four normal steps and, only if verification fails,
   one correction plus one final verification (maximum six steps).
3. Maximum one retry after the initial attempt for any provider call.
4. No ContinuousScheduler.
5. No multi-provider router.
6. No recovery supervisors, storm breakers, continuity audits, self-development,
   integrity engineering, release automation or updater activity.
7. A strict early completion rule: the goal closes only when the requested file
   exists, deterministic checks pass, sources are probed, and a fresh verification
   context returns PASS.

## First real goal

`FIELD-MVP-01`

> Investiga qué es el entrenamiento en Zona 2, cuáles son sus principales beneficios
> y cuáles son sus limitaciones, utilizando 5 fuentes fiables diferentes. Genera
> `FIELD_MVP_01.md`, de 700–1.000 palabras, con explicación breve, beneficios,
> limitaciones, conclusión y las 5 fuentes identificables.

## Single success metric

`delivery_pass`

- `true`: deliverable exists + deterministic contract passes + independent fresh
  verification passes + goal is closed.
- `false`: any of those conditions fails.
- `null`: still running.

Task counts, retries, provider calls and internal stages are diagnostics only and do
not count as progress or success.

## Evidence boundary

Local/unit tests can prove the narrow control flow only. They cannot set
`production_ready=true`. The first physical Windows execution is still pending.
