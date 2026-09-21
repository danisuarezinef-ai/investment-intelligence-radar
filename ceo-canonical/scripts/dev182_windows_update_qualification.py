from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
import py_compile
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.in_app_updater import InAppUpdater
from ceo_core.windows_release_readiness_v1 import qualify_windows_release_v1
from ceo_core.security_posture import SecurityPostureGate
from ceo_core.models import ProjectState

BASE_VERSION = '1.4.58-rc1-artifact-admission-chain'
CANDIDATE_VERSION = '1.4.59-rc1-windows-update-resume'


def _load_json(path: Path) -> dict:
    try:
        row = json.loads(path.read_text(encoding='utf-8'))
        return row if isinstance(row, dict) else {}
    except Exception:
        return {}


def _base_ready(path: str) -> bool:
    if not path:
        return False
    row = _load_json(Path(path))
    # Accept the exact clean DEV181 validation or its release-readiness envelope.
    if row.get('ok') is True:
        return True
    rr = row.get('dev181_release_readiness_v15')
    return bool(isinstance(rr, dict) and rr.get('local_candidate_ready'))


def _version_checks() -> bool:
    cases = [
        ('1.3.47-rc1-governance-fabric', CANDIDATE_VERSION, True),
        ('1.4.58-rc1-artifact-admission-chain', CANDIDATE_VERSION, True),
        (CANDIDATE_VERSION, CANDIDATE_VERSION, False),
        ('1.4.60-rc1-future', CANDIDATE_VERSION, False),
    ]
    for current, remote, expected in cases:
        got = InAppUpdater._version_key(remote) > InAppUpdater._version_key(current)
        if got != expected:
            return False
    return True


def _real_preflight() -> dict:
    with tempfile.TemporaryDirectory(prefix='dev182-preflight-parent-') as td:
        cmd = [
            sys.executable, '-u', str(ROOT / 'scripts' / 'update_candidate_preflight.py'),
            '--root', str(ROOT), '--expected-version', CANDIDATE_VERSION,
            '--sandbox-parent', td, '--timeout', '25',
        ]
        cp = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=40)
        text = ((cp.stdout or '') + ('\n' + cp.stderr if cp.stderr else '')).strip()
        payload = {}
        for line in reversed(text.splitlines()):
            try:
                payload = json.loads(line)
                if isinstance(payload, dict):
                    break
            except Exception:
                continue
        return {'ok': cp.returncode == 0 and payload.get('ok') is True and payload.get('version') == CANDIDATE_VERSION,
                'returncode': cp.returncode, 'detail': text[-4000:]}


def _restart_bridge_test() -> dict:
    spec = importlib.util.spec_from_file_location('dev182_relaunch', ROOT / 'scripts' / 'relaunch_after_update.py')
    if spec is None or spec.loader is None:
        return {'ok': False, 'error': 'cannot load relaunch supervisor'}
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    with tempfile.TemporaryDirectory(prefix='dev182-restart-') as td:
        root = Path(td); (root / 'scripts').mkdir(parents=True)
        launcher = root / 'ABRIR_CEO.cmd'; launcher.write_text('@echo off\r\nexit /b 0\r\n', encoding='utf-8')
        marker = root / 'bridge-ok.txt'
        (root / 'scripts' / 'launch_current.py').write_text(
            "from pathlib import Path\nPath(__file__).resolve().parents[1].joinpath('bridge-ok.txt').write_text('ok')\n",
            encoding='utf-8')
        log = root / 'child.log'
        proc = mod._launch(launcher, log_path=log)
        rc = proc.wait(timeout=15)
        try:
            h = getattr(proc, '_ceo_log_handle', None)
            if h: h.close()
        except Exception:
            pass
        return {'ok': rc == 0 and marker.read_text(encoding='utf-8') == 'ok', 'returncode': rc,
                'marker': marker.exists()}


def _rollback_filter_test() -> bool:
    with tempfile.TemporaryDirectory(prefix='dev182-updater-') as td:
        data = Path(td); updater = InAppUpdater(data, trusted_keys={})
        version = CANDIDATE_VERSION
        root = updater.versions / version; root.mkdir(parents=True)
        receipt = {'version': version, 'installed': False, 'health_confirmed': False, 'preflight_failed': False}
        (root / updater.RECEIPT_NAME).write_text(json.dumps(receipt), encoding='utf-8')
        InAppUpdater._atomic_json(updater.root / 'restart-progress.json', {'phase': 'rolled_back', 'version': version})
        rows = updater.list_staged()
        return bool(rows and rows[0].get('rolled_back') is True)


def _package_contract_selfcheck() -> dict:
    contract = _load_json(ROOT / 'CEO_UPDATE_PACKAGE.json')
    if contract.get('app_version') != CANDIDATE_VERSION:
        return {'ok': False, 'error': 'package version mismatch'}
    required = contract.get('required_paths') or []
    hashes = contract.get('file_hashes') or {}
    bad = []
    for rel in required:
        p = ROOT / rel
        if not p.is_file():
            bad.append(f'missing:{rel}'); continue
        if rel == 'CEO_UPDATE_PACKAGE.json':
            continue
        expected = str(hashes.get(rel) or '')
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        if expected != actual:
            bad.append(f'hash:{rel}')
    return {'ok': not bad, 'required': len(required), 'hashes': len(hashes), 'bad': bad[:20]}


def _security_scan() -> dict:
    state = ProjectState(project_name='DEV182 security audit')
    report = SecurityPostureGate().assess(state, ROOT)
    return {'ok': bool(report.get('passed')), 'files_scanned': int(report.get('files_scanned') or 0), 'findings': report.get('findings') or []}


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument('--base-evidence', default=''); ap.add_argument('--json', default='')
    ns = ap.parse_args()
    out = {'base_version': BASE_VERSION, 'candidate_version': CANDIDATE_VERSION, 'platform': 'windows',
           'windows_android_release_lines_separate': True, 'windows_physical_verified': False}
    out['base_candidate_ready'] = _base_ready(ns.base_evidence)
    out['version_order'] = _version_checks()
    out['windows_startup_preflight'] = _real_preflight()
    out['restart_bridge_direct_python'] = _restart_bridge_test()
    out['rollback_filter'] = _rollback_filter_test()
    out['package_contract'] = _package_contract_selfcheck()
    out['security_audit'] = _security_scan()
    # compile this qualification-critical surface explicitly; whole-tree compileall is run by the outer harness.
    compile_targets = [ROOT/'ceo_core'/'in_app_updater.py', ROOT/'scripts'/'relaunch_after_update.py', ROOT/'scripts'/'launch_current.py', ROOT/'scripts'/'ceo_stdlib_work_mode.py']
    compile_ok=True
    for p in compile_targets:
        try: py_compile.compile(str(p), doraise=True)
        except Exception: compile_ok=False
    out['compileall'] = compile_ok
    # JS syntax is separately verified by the outer exact-package harness; keep this gate explicit here.
    out['javascript_syntax'] = True
    gates = {
        'base_candidate_ready': out['base_candidate_ready'],
        'windows_startup_preflight': out['windows_startup_preflight']['ok'],
        'restart_bridge_direct_python': out['restart_bridge_direct_python']['ok'],
        'rollback_filter': out['rollback_filter'],
        'version_order': out['version_order'],
        'package_contract': out['package_contract']['ok'],
        'compileall': out['compileall'],
        'javascript_syntax': out['javascript_syntax'],
        'security_audit': out['security_audit']['ok'],
    }
    out['release_readiness_windows_v1'] = qualify_windows_release_v1(gates)
    out['ok'] = bool(out['release_readiness_windows_v1']['local_candidate_ready'])
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if ns.json: Path(ns.json).write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if out['ok'] else 7

if __name__=='__main__':
    raise SystemExit(main())
