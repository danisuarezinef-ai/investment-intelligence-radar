from __future__ import annotations
import ast
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
errors=[];count=0
for base in ('ceo_core','ceo_app','scripts'):
    for p in (ROOT/base).rglob('*.py'):
        count+=1
        try: tree=ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
        except SyntaxError as e: errors.append(f'{p}: {e}');continue
        for n in ast.walk(tree):
            if isinstance(n,ast.ImportFrom) and any(a.name=='*' for a in n.names):errors.append(f'{p}:{n.lineno}: wildcard import')
print({'python_files':count,'errors':errors})
raise SystemExit(1 if errors else 0)
