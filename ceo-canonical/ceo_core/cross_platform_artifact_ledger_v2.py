from __future__ import annotations
import hashlib, json
from typing import Any

ALLOWED_KINDS = {'windows_candidate','android_build_input','android_debug_apk','android_runtime_observation','campaign_checkpoint'}


def _canon(v: Any) -> bytes:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def append_artifact_v2(ledger: list[dict[str, Any]], *, kind: str, artifact_sha256: str,
                       evidence_sha256: str, claim: str) -> dict[str, Any]:
    problems: list[str] = []
    if kind not in ALLOWED_KINDS: problems.append('kind_invalid')
    for name, value in {'artifact_sha256': artifact_sha256, 'evidence_sha256': evidence_sha256}.items():
        s = str(value or '').lower()
        if len(s) != 64 or any(c not in '0123456789abcdef' for c in s): problems.append(name + '_invalid')
    if claim in {'production_verified','publication_allowed','automatic_installation'}: problems.append('forbidden_claim')
    prev = ledger[-1]['entry_sha256'] if ledger else '0' * 64
    row = {'schema_version': 2, 'ordinal': len(ledger) + 1, 'kind': kind, 'artifact_sha256': str(artifact_sha256).lower(),
           'evidence_sha256': str(evidence_sha256).lower(), 'claim': str(claim), 'prev_sha256': prev}
    row['entry_sha256'] = hashlib.sha256(_canon(row)).hexdigest()
    if not problems: ledger.append(row)
    return {'ok': not problems, 'status': 'APPENDED' if not problems else 'BLOCKED', 'problems': sorted(set(problems)), 'entry': row if not problems else None}


def verify_artifact_ledger_v2(ledger: list[dict[str, Any]]) -> dict[str, Any]:
    prev = '0' * 64
    for i, row in enumerate(ledger, 1):
        body = {k: row[k] for k in ('schema_version','ordinal','kind','artifact_sha256','evidence_sha256','claim','prev_sha256')}
        if row.get('ordinal') != i or row.get('prev_sha256') != prev or hashlib.sha256(_canon(body)).hexdigest() != row.get('entry_sha256'):
            return {'ok': False, 'status': 'BLOCKED', 'broken_ordinal': i}
        prev = row['entry_sha256']
    return {'ok': True, 'status': 'LEDGER_VALID', 'entries': len(ledger), 'head_sha256': prev}
