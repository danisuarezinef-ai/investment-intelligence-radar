#!/usr/bin/env sh
# Canonical v37 production runtime + snapshot-consistent PAPER durable reconciliation.
# REAL_TRADING remains hard-disabled.
exec python cloud_service_v37_snapshotfix.py
