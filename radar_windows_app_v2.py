"""Windows app v2 contract: installer/updater/simulator/cloud must all be healthy."""
REAL_TRADING=False

def windows_app_v2_status(*,installer_ok=False,updater_ok=False,simulator_ok=False,cloud_sync_ok=False,single_shortcut_ok=False):
    checks={'installer':bool(installer_ok),'updater':bool(updater_ok),'simulator':bool(simulator_ok),'cloud_sync':bool(cloud_sync_ok),'single_shortcut':bool(single_shortcut_ok)}
    blockers=[k for k,v in checks.items() if not v]
    return {'status':'READY_WINDOWS' if not blockers else 'BLOCKED_WINDOWS','checks':checks,'blockers':blockers,'real_trading':False}
