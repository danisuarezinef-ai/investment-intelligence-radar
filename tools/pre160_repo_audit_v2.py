"""Read-only repository debt audit for pre-1.6.

The audit nominates superseded/deletion candidates but never deletes files. A candidate can
only be removed in a separate reviewed change after dependency search and the full test suite.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

REAL_TRADING=False

CLOUD_CHAIN = [f'cloud_service_v{i}.py' for i in range(2,9)]
PROTECTED_LEGACY = {'cloud_service.py','cloud_service_v2.py','cloud_service_v3.py','cloud_service_v4.py',
                    'cloud_service_v5.py','cloud_service_v6.py','cloud_service_v7.py','cloud_service_v8.py'}
KNOWN_RECONCILED_PRS = {
    '7': ['radar_universe_pit.py','radar_investment_memory.py','radar_forward_engine.py'],
    '10': ['radar_corporate_actions.py','radar_cost_model.py','radar_simulation_readiness.py'],
    '20': ['radar_causal_runtime_v2.py','radar_causal_scoring_v2.py'],
}


def _imports(path):
    try:
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return []
    out=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import): out.extend(alias.name for alias in node.names)
        elif isinstance(node,ast.ImportFrom) and node.module: out.append(node.module)
    return out


def audit(root='.'):
    root=Path(root)
    py_files=sorted(p for p in root.glob('*.py') if p.is_file())
    names={p.name for p in py_files}
    imported_by={p.stem:set() for p in py_files}
    for p in py_files:
        for mod in _imports(p):
            top=mod.split('.')[0]
            if top in imported_by: imported_by[top].add(p.name)
    cloud={name:{'exists':name in names,'imported_by':sorted(imported_by.get(Path(name).stem,set()))} for name in CLOUD_CHAIN}
    deletion_candidates=[]
    for p in py_files:
        if p.name in PROTECTED_LEGACY or p.name.startswith('radar_') is False:
            continue
        refs=sorted(imported_by.get(p.stem,set()))
        if not refs and not p.name.startswith('radar_pre160_'):
            deletion_candidates.append({'path':p.name,'reason':'NO_TOP_LEVEL_IMPORT_REFERENCE_FOUND','safe_to_delete':False})
    reconciled={}
    for pr,paths in KNOWN_RECONCILED_PRS.items():
        reconciled[pr]={'paths':paths,'all_present':all((root/x).exists() for x in paths)}
    return {
        'status':'PASS',
        'cloud_chain':cloud,
        'legacy_pr_reconciliation':reconciled,
        'candidate_count':len(deletion_candidates),
        'deletion_candidates':deletion_candidates,
        'automatic_deletion':False,
        'deletion_requires_dependency_proof_and_full_ci':True,
        'setup_allowed':False,
        'can_trade':False,
        'real_trading':False,
    }

if __name__=='__main__':
    print(json.dumps(audit(),indent=2,ensure_ascii=False))
