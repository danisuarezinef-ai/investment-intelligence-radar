from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from browser_provider_pool import BrowserProviderRegistry


class ProviderPoolTests(unittest.TestCase):
    def test_registry_exposes_five_free_web_surfaces(self):
        root=Path(__file__).resolve().parent
        reg=BrowserProviderRegistry(base_dir=root)
        names=[x.name for x in reg.ordered()]
        self.assertEqual(names[:5],[
            "chatgpt-web","claude-web","gemini-web","perplexity-web","grok-web"
        ])
        for spec in reg.ordered():
            self.assertFalse(spec.api_required)
            self.assertTrue(spec.recipe_path.is_file())

    def test_chatgpt_preserves_existing_legacy_profile(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as td:
            reg=BrowserProviderRegistry(base_dir=root,base_port=9300)
            spec=reg.resolve("chatgpt-web",local_root=td)
            self.assertEqual(spec.profile_dir,Path(td).resolve()/"browser-profile")
            self.assertEqual(spec.port,9300)

    def test_other_providers_get_isolated_profiles_and_ports(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as td:
            reg=BrowserProviderRegistry(base_dir=root,base_port=9300)
            claude=reg.resolve("claude-web",local_root=td)
            gemini=reg.resolve("gemini-web",local_root=td)
            self.assertNotEqual(claude.profile_dir,gemini.profile_dir)
            self.assertNotEqual(claude.port,gemini.port)
            self.assertIn("browser-profiles",str(claude.profile_dir))

    def test_existing_session_can_be_selected(self):
        root=Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory() as td:
            reg=BrowserProviderRegistry(base_dir=root,base_port=9300)
            spec=reg.resolve("gemini-web",local_root=td)
            spec.profile_dir.mkdir(parents=True)
            (spec.profile_dir/"CEO_BROWSER_SESSION.json").write_text(json.dumps({
                "ok":True,"status":"SESSION_READY"
            }),encoding="utf-8")
            chosen=reg.first_with_existing_session(["gemini-web","chatgpt-web"],local_root=td)
            self.assertIsNotNone(chosen)
            self.assertEqual(chosen.name,"gemini-web")


if __name__=="__main__":
    unittest.main()
