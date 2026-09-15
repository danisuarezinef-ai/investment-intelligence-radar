#!/usr/bin/env sh
# v24 production runtime + snapshot-consistent PAPER durable reconciliation race fix
# REAL_TRADING remains hard-disabled.
exec python cloud_service_v24_snapshotfix.py
