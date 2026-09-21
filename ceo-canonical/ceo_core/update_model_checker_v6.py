from __future__ import annotations
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any

@dataclass(frozen=True, slots=True)
class StateV6:
    session_open: bool = False
    staged: bool = False
    preflight: bool = False
    active_pending: bool = False
    build_input_ok: bool = True
    license_ok: bool = False
    apk_built: bool = False
    apk_reproducible: bool = False
    api35_ok: bool = False
    api36_ok: bool = False
    same_apk: bool = True
    resume_chain_ok: bool = True
    authority_ok: bool = True
    windows_physical_ok: bool = False

ACTIONS = (
    'open_session','close_session','record_license','revoke_license','break_input','repair_input',
    'build_apk','verify_repro','break_same_apk','repair_same_apk','api35_pass','api36_pass',
    'break_resume','repair_resume','grant_forbidden','revoke_forbidden','stage','preflight','activate',
    'health_ok','rollback','windows_physical_pass'
)

def _errors(s: StateV6) -> list[str]:
    e: list[str] = []
    if s.apk_built and (not s.build_input_ok or not s.license_ok): e.append('apk_requires_inputs_and_license')
    if s.apk_reproducible and not s.apk_built: e.append('repro_requires_apk')
    if s.apk_reproducible and not s.same_apk: e.append('repro_requires_same_apk')
    if (s.api35_ok or s.api36_ok) and not s.apk_reproducible: e.append('runtime_requires_reproducible_apk')
    if s.api35_ok and s.api36_ok and not s.same_apk: e.append('dual_api_requires_same_apk')
    if s.active_pending and not (s.session_open and s.staged and s.preflight and s.resume_chain_ok and s.authority_ok): e.append('activation_requires_campaign_guards')
    if s.windows_physical_ok and s.active_pending: e.append('physical_verification_requires_settled_health')
    return e

def _step(s: StateV6, a: str) -> StateV6:
    d = asdict(s)
    if a == 'open_session' and not s.active_pending: d['session_open'] = True
    elif a == 'close_session' and not s.active_pending and not s.staged: d['session_open'] = False
    elif a == 'record_license' and not s.apk_built: d['license_ok'] = True
    elif a == 'revoke_license' and not s.apk_built: d['license_ok'] = False
    elif a == 'break_input' and not s.apk_built: d['build_input_ok'] = False
    elif a == 'repair_input' and not s.apk_built: d['build_input_ok'] = True
    elif a == 'build_apk' and s.license_ok and s.build_input_ok: d['apk_built'] = True
    elif a == 'verify_repro' and s.apk_built and s.same_apk: d['apk_reproducible'] = True
    elif a == 'break_same_apk' and not (s.api35_ok or s.api36_ok): d['same_apk'] = False; d['apk_reproducible'] = False
    elif a == 'repair_same_apk' and not (s.api35_ok or s.api36_ok): d['same_apk'] = True
    elif a == 'api35_pass' and s.apk_reproducible and s.same_apk: d['api35_ok'] = True
    elif a == 'api36_pass' and s.apk_reproducible and s.same_apk: d['api36_ok'] = True
    elif a == 'break_resume' and not s.active_pending: d['resume_chain_ok'] = False
    elif a == 'repair_resume' and not s.active_pending: d['resume_chain_ok'] = True
    elif a == 'grant_forbidden' and not s.active_pending: d['authority_ok'] = False
    elif a == 'revoke_forbidden' and not s.active_pending: d['authority_ok'] = True
    elif a == 'stage' and s.session_open and s.resume_chain_ok and s.authority_ok and not s.active_pending and not s.windows_physical_ok: d['staged'] = True; d['preflight'] = False
    elif a == 'preflight' and s.staged and s.session_open and s.resume_chain_ok and s.authority_ok: d['preflight'] = True
    elif a == 'activate' and s.staged and s.preflight and s.session_open and s.resume_chain_ok and s.authority_ok: d['active_pending'] = True
    elif a == 'health_ok' and s.active_pending: d['active_pending'] = False; d['staged'] = False; d['preflight'] = False
    elif a == 'rollback' and (s.active_pending or s.staged): d['active_pending'] = False; d['staged'] = False; d['preflight'] = False
    elif a == 'windows_physical_pass' and s.session_open and not s.active_pending and not s.staged and not s.preflight and s.resume_chain_ok and s.authority_ok: d['windows_physical_ok'] = True
    return StateV6(**d)

def bounded_model_check_v6(*, max_depth: int = 20, max_states: int = 300_000) -> dict[str, Any]:
    start = StateV6(); q = deque([(start,0)]); seen = {start}; transitions = 0; violations = []
    while q and len(seen) <= max_states:
        s, depth = q.popleft()
        errs = _errors(s)
        if errs: violations.append({'state':asdict(s),'violations':errs,'depth':depth}); break
        if depth >= max_depth: continue
        for a in ACTIONS:
            n = _step(s,a); transitions += 1; errs = _errors(n)
            if errs: violations.append({'state':asdict(n),'violations':errs,'via':a,'depth':depth+1}); q.clear(); break
            if n not in seen: seen.add(n); q.append((n,depth+1))
    return {'ok': not violations and len(seen) <= max_states, 'states_explored':len(seen), 'transitions_checked':transitions,
            'violations':violations[:3], 'truncated':len(seen)>max_states, 'max_depth':max_depth,
            'modeled_classes':['toolchain_license','build_input','apk_build','reproducibility','api35','api36','same_apk','resume_chain','authority','windows_physical']}
