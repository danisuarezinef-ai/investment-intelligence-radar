from __future__ import annotations
from typing import Any

PINNED={
 'jdk':{'version':'17','vendor_preference':'Eclipse Temurin','sha256_required':True},
 'gradle':{'version':'9.4.1','sha256':'2ab2958f2a1e51120c326cad6f385153bb11ee93b3c216c5fccebfdfbb7ec6cb'},
 'android_cli':{'revision':'15859902','sha256':'4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583'},
 'sdk_packages':['platform-tools','platforms;android-37','build-tools;37.0.0'],
}

def build_acquisition_plan_v2(*,operator_consent_ok:bool,network_available:bool,jdk17_available:bool)->dict[str,Any]:
    local=bool(operator_consent_ok and network_available and jdk17_available)
    return {'schema_version':2,'pinned':PINNED,'operator_consent_ok':bool(operator_consent_ok),
            'network_available':bool(network_available),'jdk17_available':bool(jdk17_available),
            'local_execution_ready':local,'remote_runner_eligible':bool(operator_consent_ok),
            'allow_version_relaxation':False,'allow_unverified_downloads':False,
            'next_action':'execute_local' if local else 'use_verified_internet_runner'}
