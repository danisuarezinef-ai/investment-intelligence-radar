"""Production v24 with race-safe PAPER v12 durable reconciliation."""
from __future__ import annotations
import cloud_service_v24 as base24
import radar_paper_reconciliation_racefix_v1 as racefix

REAL_TRADING=False


def main():
    installed=racefix.install()
    print('[paper-reconciliation-racefix] '+str(installed),flush=True)
    base24.main()

if __name__=='__main__':main()
