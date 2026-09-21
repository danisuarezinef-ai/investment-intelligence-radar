from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import ast

@dataclass(slots=True)
class TestQualityFinding:
    path: str
    test: str
    severity: str
    reason: str

class TestQualityAuditor:
    """Static sanity audit for tests that may pass without checking behavior."""
    def audit(self, root: str | Path) -> dict:
        root=Path(root); findings=[]; total=0
        for path in sorted(root.glob('test_*.py')):
            tree=ast.parse(path.read_text(encoding='utf-8'))
            for node in tree.body:
                if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) or not node.name.startswith('test_'):
                    continue
                total+=1
                asserts=sum(isinstance(x,ast.Assert) for x in ast.walk(node))
                explicit_raise=sum(isinstance(x,ast.Raise) for x in ast.walk(node))
                pytest_raises=sum(
                    isinstance(x, ast.Call)
                    and isinstance(x.func, ast.Attribute)
                    and isinstance(x.func.value, ast.Name)
                    and x.func.value.id == 'pytest'
                    and x.func.attr == 'raises'
                    for x in ast.walk(node)
                )
                if asserts+explicit_raise+pytest_raises==0:
                    findings.append(TestQualityFinding(str(path),node.name,'warning','No assert or explicit raise found; inspect for false-positive risk.'))
        return {'tests_scanned':total,'findings':[asdict(x) for x in findings],'passed':not findings}
