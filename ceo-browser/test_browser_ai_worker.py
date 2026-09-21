from __future__ import annotations

import json
import unittest

from browser_ai_worker import (
    BrowserResultProtocol,
    BrowserTask,
    ProgrammingPromptBuilder,
    PromptBudget,
    PromptSizer,
)


class BrowserWorkerTests(unittest.TestCase):
    def test_small_task_stays_single_turn(self):
        task = BrowserTask(
            task_id="t1",
            objective="Resume cinco puntos sobre una función pequeña.",
            acceptance=("Cinco puntos", "Respuesta breve"),
            context="def add(a,b): return a+b",
        )
        plan = PromptSizer().classify(task)
        self.assertFalse(plan.should_split)
        self.assertEqual(plan.expected_turns, 1)
        self.assertIn("<CEO_DONE>", plan.prompt)

    def test_large_task_is_flagged_before_dispatch(self):
        task = BrowserTask(
            task_id="big",
            objective="Reescribe el sistema completo",
            context="x" * 40_000,
        )
        plan = PromptSizer(PromptBudget(max_context_chars=40_000, max_prompt_chars=10_000)).classify(task)
        self.assertTrue(plan.should_split)
        self.assertIn("prompt_chars=", plan.split_reason)

    def test_result_protocol_extracts_patch_and_next(self):
        text = (
            "Cambio propuesto.\n"
            "<CEO_PATCH>--- a/x.py\n+++ b/x.py\n@@\n-old\n+new</CEO_PATCH>\n"
            "<CEO_NEXT>ejecuta tests</CEO_NEXT>\n"
            "<CEO_DONE>false</CEO_DONE>"
        )
        row = BrowserResultProtocol.parse(text)
        self.assertFalse(row["done"])
        self.assertEqual(row["next_instruction"], "ejecuta tests")
        self.assertIn("+new", row["patch"])

    def test_programming_prompt_is_bounded_and_requests_diff(self):
        task = ProgrammingPromptBuilder.first_turn(
            objective="Corrige el cálculo sin tocar otras funciones.",
            files={"calc.py": "def total(x):\n    return x * 2\n"},
            test_command="python -m unittest -q",
        )
        plan = PromptSizer().classify(task)
        self.assertTrue(task.programming)
        self.assertIn("unified diff", plan.prompt)
        self.assertIn("python -m unittest -q", plan.prompt)
        self.assertFalse(plan.should_split)


if __name__ == "__main__":
    unittest.main()
