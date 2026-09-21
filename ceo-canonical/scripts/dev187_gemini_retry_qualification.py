from pathlib import Path
import ast, json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'scripts'/'ceo_stdlib_work_mode.py'
s=p.read_text(encoding='utf-8')
ast.parse(s)
checks={
 'version':'1.4.64-rc1-gemini-retry-recovery' in s,
 'dpapi_recovery':'Gemini API key recuperada de Windows DPAPI.' in s,
 'retry_method':'async def revalidate_stored_gemini' in s,
 'retry_endpoint':'/api/session-key/revalidate' in s,
 'retry_button':'Reintentar guardada' in s,
 'validation_error_exposed':'gemini_validation_error' in s,
 'handoff_fix':'forced_checkpoint' in s and 'timeout_seconds: float = 4.0' in s,
 'no_plaintext_project_storage':'gemini_api_key.dpapi' in s and 'Windows DPAPI' in s,
}
print(json.dumps({'ok':all(checks.values()),'checks':checks},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
