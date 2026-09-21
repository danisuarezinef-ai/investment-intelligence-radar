from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from programming_browser_loop import FreeWebCodingLoop, PatchSandbox


PATCH_WRONG = """<CEO_PATCH>diff --git a/calc.py b/calc.py
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a * b
</CEO_PATCH>
<CEO_DONE>false</CEO_DONE>"""

PATCH_FIXED = """<CEO_PATCH>diff --git a/calc.py b/calc.py
--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a * b
+    return a + b
</CEO_PATCH>
<CEO_DONE>true</CEO_DONE>"""


class FakeBrowser:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def ask(self, prompt: str, *, conversation_url=None):
        self.urls.append(conversation_url)
        if not self.responses:
            raise RuntimeError("no fake response")
        return {
            "ok": True,
            "conversation_url": conversation_url or "https://chatgpt.test/c/session-1",
            "response": self.responses.pop(0),
        }


def git(root: Path, *args: str):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


class ProgrammingLoopTests(unittest.TestCase):
    def make_repo(self, td: str) -> Path:
        root = Path(td)
        git(root, "init")
        git(root, "config", "user.email", "test@example.invalid")
        git(root, "config", "user.name", "CEO Test")
        (root / "calc.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (root / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\n\n"
            "class T(unittest.TestCase):\n"
            "    def test_add(self): self.assertEqual(add(2, 3), 5)\n\n"
            "if __name__ == '__main__': unittest.main()\n",
            encoding="utf-8",
        )
        git(root, "add", ".")
        git(root, "commit", "-m", "baseline")
        return root

    def test_web_ai_can_correct_code_after_real_test_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root = self.make_repo(td)
            browser = FakeBrowser([PATCH_WRONG, PATCH_FIXED])
            loop = FreeWebCodingLoop(
                transport=browser,
                sandbox=PatchSandbox(root),
                max_turns=3,
            )
            result = loop.run(
                objective="Corrige add para que sume los dos operandos.",
                relevant_files=["calc.py", "test_calc.py"],
                test_command=["python", "-m", "unittest", "-q"],
            )
            self.assertTrue(result.success)
            self.assertEqual(result.status, "CANDIDATE_VERIFIED")
            self.assertEqual(len(result.attempts), 2)
            self.assertFalse(result.attempts[0].tests_passed)
            self.assertTrue(result.attempts[1].tests_passed)
            self.assertEqual(browser.urls[0], None)
            self.assertEqual(browser.urls[1], "https://chatgpt.test/c/session-1")
            self.assertIn("return a + b", (root / "calc.py").read_text(encoding="utf-8"))
            self.assertIn("+    return a + b", result.final_diff)

    def test_browser_failure_does_not_spawn_recovery_loop(self):
        class BrokenBrowser:
            def ask(self, prompt: str, *, conversation_url=None):
                raise RuntimeError("UI unavailable")

        with tempfile.TemporaryDirectory() as td:
            root = self.make_repo(td)
            loop = FreeWebCodingLoop(
                transport=BrokenBrowser(),
                sandbox=PatchSandbox(root),
                max_turns=3,
            )
            result = loop.run(
                objective="Corrige add.",
                relevant_files=["calc.py"],
                test_command=["python", "-m", "unittest", "-q"],
            )
            self.assertFalse(result.success)
            self.assertEqual(result.status, "BROWSER_FAIL")
            self.assertEqual(len(result.attempts), 1)


if __name__ == "__main__":
    unittest.main()
