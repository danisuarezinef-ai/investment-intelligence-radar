from pathlib import Path
import ast,json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'scripts'/'ceo_stdlib_work_mode.py'
s=p.read_text(encoding='utf-8')
ast.parse(s)
checks={
 'version':'1.4.65-rc1-gemini-key-replacement' in s,
 'recognized_state':'gemini_key_recognized' in s and 'gemini_key_status' in s,
 'quota_not_invalid':'gemini-key-recognized-blocked' in s,
 'replacement_persists':'Explicit user replacement' in s and '_save_windows_dpapi_gemini_key(key)' in s,
 'ui_distinguishes':'Nueva clave reconocida y guardada' in s,
 'execution_not_overclaimed':'self.execution_enabled = False' in s and 'LIVE_VERIFIED' in s,
 'handoff_fix':'forced_checkpoint' in s and 'timeout_seconds: float = 4.0' in s,
}
print(json.dumps({'ok':all(checks.values()),'checks':checks},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
