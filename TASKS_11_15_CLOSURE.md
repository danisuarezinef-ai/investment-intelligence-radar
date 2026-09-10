# Tasks 11–15 closure

Date: 2026-09-10
Target release: 1.5.21

## 11. Windows ↔ Cloud contract

Required contract: /health, /snapshot, /dashboard-v2, /notifications, /pc-sync, /node-heartbeat and /validation-v3. The desktop cache now includes validation-v3 and records per-endpoint health/details. Optional HTTP 404 responses enter a 15-minute per-endpoint backoff instead of being retried every minute.

## 12. Version / identity coherence

Visible product identity remains `Radar de Inversión`. Compatibility identities remain stable: `InvestmentIntelligenceRadar.exe`, `RadarSimulationLab.exe`, `RadarWorker.exe`, `RadarUpdater.exe`, existing local data directory/AppId, update-channel filenames and `Radar_de_Inversion_Setup.exe`. Static installer/sync versions are aligned to 1.5.21 and the Windows build stamps runtime versions from version.json.

## 13. Tests

Dedicated closure tests cover required Windows/Cloud endpoints, 404 backoff, identity/version compatibility, full-suite/Windows release workflow gates and the REAL_TRADING boundary. Final status remains NOT VERIFIED until CI and Windows builds complete successfully.

## 14. Production deployment

A manual Railway redeploy during audit reused the old `e22d567...` snapshot and therefore is explicitly rejected as evidence of current production. Closure requires a fresh deployment whose commit hash equals the final merged `main` SHA, status SUCCESS, start command `python cloud_service_v3.py`, healthcheck `/health`, and externally/operationally verified endpoints.

## 15. No real trading

REAL_TRADING remains FALSE. No broker, broker credentials, real order submission, live capital, auto-enable or automatic promotion to real trading is introduced. PAPER and SHADOW only.
