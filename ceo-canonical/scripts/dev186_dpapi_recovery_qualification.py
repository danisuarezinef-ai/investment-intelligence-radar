from pathlib import Path
import ast, json
ROOT=Path(__file__).resolve().parents[1]
p=ROOT/'scripts'/'ceo_stdlib_work_mode.py'
s=p.read_text(encoding='utf-8')
ast.parse(s)
checks={
 'version':'1.4.63-rc1-dpapi-recovery' in s,
 'powershell_load_fallback':'_load_windows_dpapi_gemini_key_via_powershell' in s,
 'powershell_save_fallback':'_save_windows_dpapi_gemini_key_via_powershell' in s,
 'plausible_key_loader':'return _plausible_gemini_key(plain)' in s,
 'safe_prompt':'se guardará cifrada con Windows DPAPI' in s,
 'handoff_fix':'forced_checkpoint' in s and 'timeout_seconds: float = 4.0' in s,
}
print(json.dumps({'ok':all(checks.values()),'checks':checks},ensure_ascii=False,indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
