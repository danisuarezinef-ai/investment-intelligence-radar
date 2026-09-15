# CEO de IAs update transport

This branch is an isolated transport channel for CEO de IAs updates. It is not merged into Radar main and does not alter Radar production code.

Stable manifest:
`ceo-updates/manifest.json`

Security model:
- HTTPS manifest
- SHA-256 required
- ZIP inspection before staging
- current version kept intact
- installation/restart requires explicit human confirmation
- no automatic promotion
