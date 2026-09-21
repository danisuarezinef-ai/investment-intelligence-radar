from __future__ import annotations

import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PATTERNS={
    'openai_key': re.compile(r'\bsk-[A-Za-z0-9_-]{20,}\b'),
    'google_key': re.compile(r'\bAIza[A-Za-z0-9_-]{20,}\b'),
    'private_key': re.compile(r'BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY'),
}
EXCLUDE={'.git','.venv','__pycache__','.pytest_cache','data','dist','build'}

def main():
    findings=[]
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(part in EXCLUDE for part in path.parts): continue
        if path.suffix.lower() not in {'.py','.md','.txt','.toml','.yml','.yaml','.json','.html','.ps1','.iss','.example'} and path.name!='.env.example': continue
        try:text=path.read_text(encoding='utf-8',errors='ignore')
        except Exception:continue
        for name,rx in PATTERNS.items():
            if rx.search(text):findings.append({'file':str(path.relative_to(ROOT)),'pattern':name})
    print({'files_scanned':'source tree','findings':findings})
    raise SystemExit(1 if findings else 0)
if __name__=='__main__':main()
