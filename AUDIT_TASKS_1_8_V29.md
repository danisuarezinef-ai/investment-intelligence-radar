# Radar de Inversión — Auditoría tareas 1–8 v29

Fecha: 2026-09-10
Base auditada: `e22d5670fd12b07e0ec1b60d402f0932e181efe9` (Research v28)

## Hallazgos confirmados

- Railway production desplegó exactamente el SHA de `main` auditado y el deployment observado está en SUCCESS.
- La autoridad persistente restauró evidencia forward exacta tras deployment sin backfill ni reconstrucción y con `real_trading=false`.
- Supabase conserva evidencia prospectiva y estado autónomo; no se observaron duplicados de claves/orígenes en el ledger forward ni en soak.
- El soak sigue en fase de acumulación: no han transcurrido todavía 24 h, por lo que no puede declararse PASS final.
- Los 16 activos configurados tienen snapshots persistidos. La persistencia Supabase observada para market snapshots se quedó por detrás del runtime cloud y requiere seguimiento de la ruta de sync.
- Se observó un timeout/HTTP 500 transitorio en forward outcome sync, seguido por recuperación idempotente.
- Research v28 separa cronológicamente las ventanas OOS y mantiene SIMULATED aislado de PAPER/LIVE, pero el evaluador base incluía el precio de la sesión actual en el cálculo de momentum antes de ejecutar a ese mismo precio: same-close lookahead.

## Corrección v29

- `radar_simulation_research_v3.py`: los signals usan exclusivamente history previa a la sesión de ejecución (`SIGNAL_LAG_DAYS=1`). El día actual se incorpora a history después de decisiones/ejecuciones.
- `radar_simulation_research_v5.py`: propaga `signal_lag_days=1`, `lookahead=false` y `sealed_final_test=false`; deja explícito que los test folds son medidas OOS de investigación, no un final test sellado.
- `tests/test_research_tasks_6_10_v28.py`: regresión donde un salto extremo exclusivamente en el cierre actual no puede generar una operación en ese mismo cierre.

## Seguridad

- `REAL_TRADING=false` permanece inalterado.
- No broker real, órdenes reales ni auto-promoción.
- Esta rama no se ha fusionado ni desplegado. Requiere CI/Windows PASS antes de considerar merge.
