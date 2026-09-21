from __future__ import annotations

import hashlib
import json
from typing import Any

REQUIRED_PROBES = ('launch', 'core_health', 'process_death', 'explicit_reboot', 'force_stop_relaunch', 'storage_pressure_cleanup')


def _sha(v: Any) -> bool:
    s = str(v or '').strip().lower(); return len(s) == 64 and all(c in '0123456789abcdef' for c in s)


def _canon(v: Any) -> bytes:
    return json.dumps(v, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def build_runtime_observation_v3(*, api_level: int, apk_sha256: str, input_identity_sha256: str,
                                 device_identity_sha256: str, boot_identity_sha256: str,
                                 source: str, probes: dict[str, bool]) -> dict[str, Any]:
    problems: list[str] = []
    if int(api_level) not in (35, 36): problems.append('api_level_invalid')
    for key, value in {'apk_sha256': apk_sha256, 'input_identity_sha256': input_identity_sha256,
                       'device_identity_sha256': device_identity_sha256, 'boot_identity_sha256': boot_identity_sha256}.items():
        if not _sha(value): problems.append(key + '_invalid')
    if source not in {'android_emulator', 'physical_android'}: problems.append('source_invalid')
    normalized = {k: bool(probes.get(k, False)) for k in REQUIRED_PROBES}
    if not all(normalized.values()): problems.append('required_probe_failed_or_missing')
    row = {
        'schema_version': 3, 'api_level': int(api_level), 'apk_sha256': str(apk_sha256).lower(),
        'input_identity_sha256': str(input_identity_sha256).lower(), 'device_identity_sha256': str(device_identity_sha256).lower(),
        'boot_identity_sha256': str(boot_identity_sha256).lower(), 'source': source, 'probes': normalized,
        'runtime_pass': not problems, 'physical_device': source == 'physical_android', 'production_verified': False,
    }
    row['observation_sha256'] = hashlib.sha256(_canon(row)).hexdigest()
    return {'ok': not problems, 'status': 'RUNTIME_OBSERVATION_VALID' if not problems else 'BLOCKED', 'problems': sorted(set(problems)), **row}
