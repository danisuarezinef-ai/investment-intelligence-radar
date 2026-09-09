"""Release guard for Windows/PAPER production artifacts.

A release is publishable only when the relevant CI/build/smoke and safety invariants are verified.
"""
REAL_TRADING=False


def release_guard(*, core_ci=False, windows_build=False, simulation_smoke=False, installer_verified=False, updater_verified=False, forward_integrity=False, real_trading_flag=False):
    checks={
        'core_ci':bool(core_ci),
        'windows_build':bool(windows_build),
        'simulation_smoke':bool(simulation_smoke),
        'installer_verified':bool(installer_verified),
        'updater_verified':bool(updater_verified),
        'forward_integrity':bool(forward_integrity),
        'real_trading_off':real_trading_flag is False,
    }
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'RELEASE_READY' if not blockers else 'BLOCKED','checks':checks,'blockers':blockers,'real_trading':False}
