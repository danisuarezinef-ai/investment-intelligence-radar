from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
B = REPO / "ceo-browser"


def must(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"{label}: missing {needle!r}")


def must_not(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"{label}: forbidden {needle!r}")


def main() -> int:
    wrapper = (B / "run_w14b_real_session_gate.ps1").read_text(encoding="utf-8")
    restart = (B / "run_browser_restart_gate.ps1").read_text(encoding="utf-8")
    launcher = (B / "EJECUTAR_W14B_SESION_REAL.cmd").read_text(encoding="utf-8")
    recipe = json.loads((B / "recipes" / "chatgpt_web.json").read_text(encoding="utf-8"))
    builder = (B / "build_first_trial_lab.py").read_text(encoding="utf-8")

    # W14-B must reuse the already-audited restart engine instead of duplicating it.
    must(wrapper, 'run_browser_restart_gate.ps1', "wrapper")
    must(wrapper, 'open_chatgpt_profile.ps1', "wrapper")
    must(wrapper, 'windows_chatgpt_cdp_driver.ps1', "wrapper")
    must(wrapper, 'recipes\\chatgpt_web.json', "wrapper")
    must(wrapper, 'W14B_REAL_CHATGPT_SESSION_PASS', "wrapper")
    must(wrapper, 'W14B_REAL_SESSION_PENDING_OR_FAILED', "wrapper")
    must(wrapper, 'pre_restart_session_ready=$true', "wrapper")
    must(wrapper, 'post_restart_session_ready=$true', "wrapper")
    must(wrapper, 'real_chatgpt_verified=$true', "wrapper")
    must(wrapper, 'windows_physical_verified=$true', "wrapper")
    must(wrapper, 'api_calls=0', "wrapper")
    must(wrapper, 'paid_api_calls=0', "wrapper")
    must(wrapper, 'manual_login_only=$true', "wrapper")
    must(wrapper, 'captcha_bypass=$false', "wrapper")
    must(wrapper, 'two_factor_bypass=$false', "wrapper")

    # Success evidence may only be emitted after restart + final session probe checks.
    assert wrapper.index('BROWSER_RESTART_SAME_CONVERSATION_PASS') < wrapper.index('real_chatgpt_verified=$true')
    assert wrapper.index('POST_RESTART_SESSION_PROBE') < wrapper.index('real_chatgpt_verified=$true')
    assert wrapper.index('SESSION_READY') < wrapper.index('real_chatgpt_verified=$true')

    # The underlying engine must physically close and relaunch, preserving conversation.
    must(restart, 'CloseBrowserAfter', "restart")
    must(restart, 'BROWSER_RESTART_SAME_CONVERSATION_PASS', "restart")
    must(restart, 'browser_closed_between_turns=$true', "restart")
    must(restart, 'browser_relaunched=$true', "restart")
    must(restart, 'same_conversation=$same', "restart")
    must_not(restart, 'ConversationUrl",$ConversationUrl,"-NoLaunch"', "restart")

    # Real provider recipe and safety boundaries.
    assert recipe.get("url") == "https://chatgpt.com/"
    constraints = dict(recipe.get("constraints") or {})
    assert constraints.get("manual_login_allowed") is True
    assert constraints.get("no_captcha_bypass") is True
    assert constraints.get("no_2fa_bypass") is True
    assert constraints.get("no_purchase") is True
    assert constraints.get("no_subscription_change") is True

    # One-click launcher must call only the W14-B gate.
    must(launcher, 'run_w14b_real_session_gate.ps1', "launcher")
    must_not(launcher.lower(), 'git push', "launcher")
    must_not(launcher.lower(), 'current.json', "launcher")

    # Portable LAB must carry both the wrapper and launcher.
    must(builder, '"run_w14b_real_session_gate.ps1"', "builder")
    must(builder, '"EJECUTAR_W14B_SESION_REAL.cmd"', "builder")

    print("W14B_REAL_SESSION_RUNNER_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
