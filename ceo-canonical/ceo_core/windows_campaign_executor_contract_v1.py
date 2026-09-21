from __future__ import annotations
from typing import Any

ALLOWED = ('verify_candidate_hash', 'baseline_health', 'collect_evidence', 'run_preflight', 'pause_for_human_gate', 'write_checkpoint')
FORBIDDEN = ('install', 'publish', 'promote', 'purchase', 'real_trade', 'delete_user_data')


def build_windows_campaign_executor_contract_v1(*, candidate_sha256: str, campaign_bundle_sha256: str) -> dict[str, Any]:
    problems: list[str] = []
    for key, value in {'candidate_sha256': candidate_sha256, 'campaign_bundle_sha256': campaign_bundle_sha256}.items():
        s = str(value or '').lower()
        if len(s) != 64 or any(c not in '0123456789abcdef' for c in s): problems.append(key + '_invalid')
    return {
        'ok': not problems, 'status': 'EXECUTOR_CONTRACT_READY' if not problems else 'BLOCKED',
        'problems': sorted(set(problems)), 'candidate_sha256': candidate_sha256, 'campaign_bundle_sha256': campaign_bundle_sha256,
        'allowed_actions': list(ALLOWED), 'forbidden_actions': list(FORBIDDEN), 'requires_human_start': True,
        'requires_human_cutover_confirmation': True, 'can_install_unattended': False, 'can_publish': False,
        'can_spend': False, 'windows_physical_verified': False,
    }


def validate_executor_action_v1(action: str) -> dict[str, Any]:
    a = str(action or '')
    return {'ok': a in ALLOWED, 'action': a, 'blocked': a not in ALLOWED, 'forbidden': a in FORBIDDEN}
