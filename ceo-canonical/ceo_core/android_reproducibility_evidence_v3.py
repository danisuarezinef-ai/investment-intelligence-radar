from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as fh:
        for b in iter(lambda:fh.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def verify_reproducibility_evidence_v3(first_apk: str | Path, second_apk: str | Path, *, expected_sha256: str) -> dict[str, Any]:
    a,b=Path(first_apk),Path(second_apk); problems=[]
    if not a.is_file(): problems.append('first_apk_missing')
    if not b.is_file(): problems.append('second_apk_missing')
    if problems: return {'schema_version':3,'ok':False,'status':'INCOMPLETE_EVIDENCE','problems':problems,'production_verified':False}
    sa,sb=_sha(a),_sha(b); za,zb=a.stat().st_size,b.stat().st_size
    if sa!=sb: problems.append('sha256_mismatch')
    if za!=zb: problems.append('size_mismatch')
    if expected_sha256 and sa!=expected_sha256: problems.append('expected_sha256_mismatch')
    ok=not problems
    return {'schema_version':3,'ok':ok,'status':'BYTE_REPRODUCIBILITY_VERIFIED' if ok else 'BLOCKED','problems':problems,
            'apk_sha256':sa if ok else None,'size_bytes':za if ok else None,'two_distinct_paths':a.resolve()!=b.resolve(),
            'byte_identical':ok,'production_verified':False}
