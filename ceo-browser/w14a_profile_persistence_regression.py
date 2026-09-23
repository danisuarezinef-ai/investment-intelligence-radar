from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

ROOT = Path(os.environ["CEO_W14_ROOT"]).resolve()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    driver_rel = "ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1"
    profile_rel = "ceo_core/browser_ai/open_chatgpt_profile.ps1"
    recipe_rel = "ceo_core/browser_ai/recipes/chatgpt_web.json"
    provider_rel = "ceo_core/providers/chatgpt_web.py"

    driver = (ROOT / driver_rel).read_text(encoding="utf-8")
    profile = (ROOT / profile_rel).read_text(encoding="utf-8")
    recipe = json.loads((ROOT / recipe_rel).read_text(encoding="utf-8"))
    provider = (ROOT / provider_rel).read_text(encoding="utf-8")

    assert "Get-CDPOwnership" in driver
    assert "BROWSER_PROFILE_OWNERSHIP_CONFLICT" in driver
    assert "matched_profile_processes" in driver
    assert "$profileArg='--user-data-dir=" in driver
    assert "Get-CimInstance Win32_Process" in driver
    assert "Prune-UnrelatedRestoredTargets" in driver

    assert 'exclusive_profile=$true' in profile
    assert 'profile_dir=$ProfileDir' in profile
    assert 'validated_at=(Get-Date).ToString("s")' in profile
    assert "no intenta saltarse CAPTCHA ni 2FA" in profile

    constraints = dict(recipe.get("constraints") or {})
    assert constraints.get("no_captcha_bypass") is True
    assert constraints.get("no_2fa_bypass") is True
    assert constraints.get("manual_login_allowed") is True
    assert constraints.get("no_purchase") is True
    assert constraints.get("no_subscription_change") is True

    assert '"CEO de IAs" / "browser-profile"' in provider
    assert "persistent so the human can log in once and CEO can reuse the session" in provider

    contract = json.loads((ROOT / "CEO_UPDATE_PACKAGE.json").read_text(encoding="utf-8"))
    hashes = dict(contract.get("file_hashes") or {})
    for rel in (driver_rel, profile_rel, recipe_rel, provider_rel):
        actual = sha(ROOT / rel)
        assert hashes.get(rel) == actual, (rel, hashes.get(rel), actual)

    print("W14A_PROFILE_CONTRACT_REGRESSION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
