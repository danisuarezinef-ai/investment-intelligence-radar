"""Production v37 with race-safe PAPER durable reconciliation."""
from __future__ import annotations
import cloud_service_v37 as base37
import radar_paper_reconciliation_racefix_v1 as racefix

REAL_TRADING=False


def main():
    installed=racefix.install()
    print('[paper-reconciliation-racefix] '+str(installed),flush=True)
    base37.main()


if __name__=='__main__':
    main()
