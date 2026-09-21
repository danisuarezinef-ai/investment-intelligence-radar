from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from first_real_goal_mode import MVPFieldRunner


def make_report(words_target: int = 780) -> str:
    headings = [
        "## Qué es el entrenamiento en Zona 2",
        "## Beneficios",
        "## Limitaciones",
        "## Conclusión",
        "## Fuentes",
    ]
    paragraphs = []
    base = (
        "La intensidad moderada permite sostener un esfuerzo aeróbico controlado y debe "
        "interpretarse según el contexto individual, el método de medición y el objetivo del entrenamiento. "
    )
    while len(("\n".join(paragraphs)).split()) < max(650, words_target - 130):
        paragraphs.append(base)
    sources = "\n".join(
        f"- Fuente {i}: Organización {i}, 2025, https://example{i}.org/source"
        for i in range(1, 6)
    )
    return (
        f"{headings[0]}\n\n{''.join(paragraphs[:10])}\n\n"
        f"{headings[1]}\n\n{''.join(paragraphs[10:20])}\n\n"
        f"{headings[2]}\n\n{''.join(paragraphs[20:30])}\n\n"
        f"{headings[3]}\n\n{''.join(paragraphs[30:])}\n\n"
        f"{headings[4]}\n\n{sources}\n"
    )


class QueueProvider:
    name = "gemini-interactions"

    def __init__(self, queue):
        self.queue = queue

    async def generate(self, prompt: str, *, max_output_tokens: int) -> str:
        if not self.queue:
            raise AssertionError("provider queue exhausted")
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def factory_for(queue):
    return lambda: QueueProvider(queue)


async def reachable_source(url: str):
    return {"url": url, "reachable": True, "status": 200, "title": "Synthetic test source", "reason": "ok"}


def research_json():
    return json.dumps(
        {
            "notes": "Notas suficientes sobre definición, beneficios y limitaciones.",
            "sources": [
                {
                    "title": f"Fuente {i}",
                    "publisher": f"Organización {i}",
                    "year": "2025",
                    "url": f"https://example{i}.org/source",
                    "relevance": "relevante",
                }
                for i in range(1, 6)
            ],
        },
        ensure_ascii=False,
    )


PASS_VERIFY = json.dumps(
    {
        "pass": True,
        "reasons": [],
        "checks": {
            "answers_goal": True,
            "benefits_balanced": True,
            "limitations_present": True,
            "sources_identifiable": True,
            "sources_plausibly_relevant": True,
            "no_obvious_fabrication": True,
        },
    }
)

FAIL_VERIFY = json.dumps(
    {
        "pass": False,
        "reasons": ["borrador insuficiente"],
        "checks": {
            "answers_goal": False,
            "benefits_balanced": False,
            "limitations_present": True,
            "sources_identifiable": True,
            "sources_plausibly_relevant": True,
            "no_obvious_fabrication": True,
        },
    }
)


class MVPFieldTests(unittest.IsolatedAsyncioTestCase):
    async def test_happy_path_closes_with_one_binary_metric(self):
        queue = [research_json(), make_report(), PASS_VERIFY]
        with tempfile.TemporaryDirectory() as td:
            runner = MVPFieldRunner(
                provider_factory=factory_for(queue),
                results_root=td,
                source_probe=reachable_source,
            )
            result = await runner.run()
            self.assertTrue(result["delivery_pass"])
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["stage"], "closed")
            self.assertTrue((Path(td) / "FIELD_MVP_01.md").is_file())
            self.assertLessEqual(len(result["steps"]), 4)
            self.assertTrue(result["verifier"]["pass"])
            self.assertTrue(result["deterministic_checks"]["word_count_ok"])
            self.assertTrue(result["deterministic_checks"]["headings_ok"])
            self.assertTrue(result["deterministic_checks"]["source_count_ok"])

    async def test_one_correction_then_final_verify_max_six_steps(self):
        too_short = (
            "## Qué es el entrenamiento en Zona 2\nBreve.\n"
            "## Beneficios\nBreve.\n## Limitaciones\nBreve.\n"
            "## Conclusión\nBreve.\n## Fuentes\n"
            + "\n".join(f"- https://example{i}.org/source" for i in range(1, 6))
        )
        queue = [research_json(), too_short, FAIL_VERIFY, make_report(), PASS_VERIFY]
        with tempfile.TemporaryDirectory() as td:
            runner = MVPFieldRunner(
                provider_factory=factory_for(queue),
                results_root=td,
                source_probe=reachable_source,
            )
            result = await runner.run()
            self.assertTrue(result["delivery_pass"])
            names = [x["name"] for x in result["steps"]]
            self.assertIn("single_correction", names)
            self.assertIn("final_verify", names)
            self.assertLessEqual(len(names), 6)

    async def test_provider_failure_stops_after_one_retry_without_recovery_layers(self):
        queue = [RuntimeError("offline-1"), RuntimeError("offline-2")]
        with tempfile.TemporaryDirectory() as td:
            runner = MVPFieldRunner(
                provider_factory=factory_for(queue),
                results_root=td,
                source_probe=reachable_source,
            )
            result = await runner.run()
            self.assertFalse(result["delivery_pass"])
            self.assertEqual(result["status"], "failed")
            research = next(x for x in result["steps"] if x["name"] == "research")
            self.assertEqual(research["attempts"], 2)
            self.assertEqual(research["status"], "failed")
            self.assertEqual(len(queue), 0)


if __name__ == "__main__":
    unittest.main()
