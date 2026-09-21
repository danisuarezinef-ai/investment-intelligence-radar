from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile, BadZipFile


def inspect_apk_v1(path: str | Path, *, expected_sha256: str = '') -> dict[str, Any]:
    p = Path(path)
    problems: list[str] = []
    if not p.is_file():
        return {'ok': False, 'status': 'BLOCKED', 'problems': ['apk_missing'], 'production_verified': False}
    raw = p.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 and digest != str(expected_sha256).lower(): problems.append('apk_sha256_mismatch')
    names: list[str] = []
    encrypted = 0
    try:
        with ZipFile(p) as zf:
            infos = zf.infolist()
            names = [x.filename for x in infos]
            if len(names) != len(set(names)): problems.append('duplicate_zip_path')
            for info in infos:
                q = PurePosixPath(info.filename)
                if q.is_absolute() or '..' in q.parts: problems.append('unsafe_zip_path')
                if info.flag_bits & 0x1: encrypted += 1
            if encrypted: problems.append('encrypted_entry')
            if 'AndroidManifest.xml' not in names: problems.append('manifest_missing')
            dex = [n for n in names if n.startswith('classes') and n.endswith('.dex')]
            if not dex: problems.append('classes_dex_missing')
    except BadZipFile:
        problems.append('apk_not_zip')
        dex = []
    return {
        'ok': not problems,
        'status': 'APK_STRUCTURE_VALID' if not problems else 'BLOCKED',
        'problems': sorted(set(problems)),
        'apk_sha256': digest,
        'size_bytes': len(raw),
        'entry_count': len(names),
        'dex_count': len(dex) if 'dex' in locals() else 0,
        'offline_only': True,
        'signature_verified': False,
        'runtime_verified': False,
        'production_verified': False,
    }
