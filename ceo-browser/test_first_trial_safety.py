from __future__ import annotations

import json
import socket
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from first_trial_safety import (
    FirstTrialReport,
    audit_first_trial_package,
    bounded_text,
    choose_cdp_port,
    go_criteria,
    profile_marker_status,
    redact_secrets,
    run_preflight,
)


class FirstTrialSafetyTests(unittest.TestCase):
    def test_secret_redaction_and_log_bound(self):
        raw="Authorization: Bearer topsecret123\napi_key=AIzaABCDEFGHIJKLMNOPQRSTUVWXY\nhello"
        clean=redact_secrets(raw)
        self.assertNotIn("topsecret123",clean)
        self.assertNotIn("AIzaABCDEFGHIJKLMNOPQRSTUVWXY",clean)
        out=bounded_text("x"*300000,max_bytes=4096)
        self.assertLessEqual(len(out.encode("utf-8")),4096)
        self.assertIn("CEO_LOG_TRUNCATED",out)

    def test_choose_port_falls_back_when_preferred_is_occupied(self):
        sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        sock.bind(("127.0.0.1",0))
        port=sock.getsockname()[1]
        try:
            selected,reason=choose_cdp_port(port,span=4)
            self.assertNotEqual(selected,port)
            self.assertEqual(reason,"fallback-free")
        finally:
            sock.close()

    def test_profile_fresh_is_writable_and_marker_can_be_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/"profile"
            first=profile_marker_status(root)
            self.assertTrue(first["writable"])
            self.assertFalse(first["marker_present"])
            (root/"CEO_BROWSER_PROFILE.json").write_text(json.dumps({
                "exclusive_profile":True,
            }),encoding="utf-8")
            second=profile_marker_status(root)
            self.assertTrue(second["exclusive_profile"])

    def test_go_criteria_requires_physical_field_state(self):
        r=FirstTrialReport(status="GO")
        no_field=go_criteria(r,None)
        self.assertFalse(no_field["first_autodevelopment_launch_allowed"])
        field={
            "BROWSER_FIELD_VERIFIED":True,
            "api_calls_required":0,
            "production_promotion_allowed":False,
            "automatic_merge_allowed":False,
        }
        yes=go_criteria(r,field)
        self.assertTrue(yes["first_autodevelopment_launch_allowed"])
        field["automatic_merge_allowed"]=True
        self.assertFalse(go_criteria(r,field)["first_autodevelopment_launch_allowed"])

    def test_package_manifest_for_current_tree(self):
        root=Path(__file__).resolve().parent
        row=audit_first_trial_package(root)
        self.assertTrue(row["ok"],row)
        self.assertEqual(row["present_count"],row["required_count"])
        self.assertTrue(all(len(x)==64 for x in row["hashes"].values()))

    def test_preflight_generates_distinct_ci_and_physical_state(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            report=run_preflight(
                browser_ai_dir=root,
                profile_dir=td/"profile",
                evidence_dir=td/"evidence",
                preferred_port=19327,
            )
            self.assertTrue((td/"evidence"/"FIRST_TRIAL_PREFLIGHT.json").is_file())
            ids={x["id"] for x in report.checks}
            self.assertIn("package-manifest",ids)
            self.assertIn("no-openai-api",ids)
            self.assertIn("separate-b38",ids)


if __name__=="__main__":
    unittest.main()
