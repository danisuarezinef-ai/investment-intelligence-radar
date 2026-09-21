from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TaskSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


@dataclass(frozen=True)
class PromptBudget:
    max_context_chars: int = 18_000
    max_prompt_chars: int = 22_000
    target_turns: int = 1
    hard_max_turns: int = 4


@dataclass(frozen=True)
class BrowserTask:
    task_id: str
    objective: str
    acceptance: tuple[str, ...] = ()
    context: str = ""
    expected_artifact: str | None = None
    programming: bool = False


@dataclass
class BrowserConversationState:
    conversation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    conversation_url: str | None = None
    turns: int = 0
    provider: str = "chatgpt-web"
    finished: bool = False
    last_response: str = ""


@dataclass(frozen=True)
class PromptPlan:
    task_id: str
    prompt: str
    task_size: TaskSize
    expected_turns: int
    should_split: bool
    split_reason: str = ""


class PromptSizer:
    """Keep work units inside the practical size of one web-IA answer.

    This is deliberately heuristic. The policy is conservative: if the request is
    too large, CEO splits it before dispatch instead of hoping for a 30-minute answer.
    """

    def __init__(self, budget: PromptBudget | None = None) -> None:
        self.budget = budget or PromptBudget()

    def classify(self, task: BrowserTask) -> PromptPlan:
        context = task.context[: self.budget.max_context_chars]
        acceptance = "\n".join(f"- {x}" for x in task.acceptance) or "- Deliver the requested result completely."
        mode = (
            "You are solving one bounded programming work unit."
            if task.programming
            else "You are solving one bounded work unit."
        )
        response_rule = (
            "Return only the requested substantive result. Do not create a long plan. "
            "Do not ask me to say continue. If the task does not fit in one good answer, "
            "finish one coherent sub-result and end with <CEO_NEXT>one precise next step</CEO_NEXT>."
        )
        artifact_rule = ""
        if task.expected_artifact:
            artifact_rule = (
                f"\nEXPECTED ARTIFACT: {task.expected_artifact}\n"
                "If this is a programming task, return complete file content or a unified diff inside "
                "<CEO_PATCH>...</CEO_PATCH>; do not claim a file was written."
            )
        prompt = (
            f"{mode}\n\n"
            f"OBJECTIVE:\n{task.objective.strip()}\n\n"
            f"ACCEPTANCE:\n{acceptance}\n\n"
            f"CONTEXT:\n{context.strip() or '(none)'}\n"
            f"{artifact_rule}\n"
            f"OPERATING RULE:\n{response_rule}\n"
            f"End with <CEO_DONE>true|false</CEO_DONE>."
        ).strip()

        signal = len(task.objective) + len(context) + sum(len(x) for x in task.acceptance)
        if signal <= 7_000:
            size, turns = TaskSize.SMALL, 1
        elif signal <= 15_000:
            size, turns = TaskSize.MEDIUM, 2
        else:
            size, turns = TaskSize.LARGE, 3

        should_split = len(prompt) > self.budget.max_prompt_chars or turns > self.budget.hard_max_turns
        reason = ""
        if len(prompt) > self.budget.max_prompt_chars:
            reason = f"prompt_chars={len(prompt)}>{self.budget.max_prompt_chars}"
        elif turns > self.budget.hard_max_turns:
            reason = f"expected_turns={turns}>{self.budget.hard_max_turns}"

        return PromptPlan(
            task_id=task.task_id,
            prompt=prompt[: self.budget.max_prompt_chars],
            task_size=size,
            expected_turns=turns,
            should_split=should_split,
            split_reason=reason,
        )


class BrowserResultProtocol:
    DONE_RE = re.compile(r"<CEO_DONE>\s*(true|false)\s*</CEO_DONE>", re.I)
    NEXT_RE = re.compile(r"<CEO_NEXT>(.*?)</CEO_NEXT>", re.I | re.S)
    PATCH_RE = re.compile(r"<CEO_PATCH>(.*?)</CEO_PATCH>", re.I | re.S)

    @classmethod
    def parse(cls, text: str) -> dict[str, Any]:
        value = str(text or "").strip()
        done_match = cls.DONE_RE.search(value)
        next_match = cls.NEXT_RE.search(value)
        patch_match = cls.PATCH_RE.search(value)
        return {
            "text": value,
            "done": (done_match.group(1).lower() == "true") if done_match else None,
            "next_instruction": next_match.group(1).strip() if next_match else None,
            "patch": patch_match.group(1).strip() if patch_match else None,
        }


class ProgrammingPromptBuilder:
    """Build small coding turns that a web AI can realistically answer."""

    @staticmethod
    def first_turn(
        *,
        objective: str,
        files: dict[str, str],
        test_command: str,
        max_file_chars: int = 30_000,
    ) -> BrowserTask:
        chunks: list[str] = []
        for path, content in files.items():
            chunks.append(
                f"FILE: {path}\n---BEGIN FILE---\n{str(content)[:max_file_chars]}\n---END FILE---"
            )
        context = "\n\n".join(chunks)
        return BrowserTask(
            task_id=f"code-{uuid.uuid4().hex[:10]}",
            objective=objective,
            acceptance=(
                "Make the smallest change that satisfies the objective.",
                "Do not change unrelated behavior.",
                f"The candidate must pass: {test_command}",
                "Return a unified diff in <CEO_PATCH> tags.",
            ),
            context=context,
            programming=True,
        )

    @staticmethod
    def correction_turn(
        *,
        objective: str,
        previous_patch: str,
        test_output: str,
        relevant_files: dict[str, str],
        test_command: str,
    ) -> BrowserTask:
        file_context = "\n\n".join(
            f"FILE NOW: {p}\n---BEGIN FILE---\n{c[:24_000]}\n---END FILE---"
            for p, c in relevant_files.items()
        )
        context = (
            f"PREVIOUS PATCH:\n{previous_patch[:18_000]}\n\n"
            f"TEST COMMAND:\n{test_command}\n\n"
            f"TEST OUTPUT:\n{test_output[:12_000]}\n\n"
            f"{file_context}"
        )
        return BrowserTask(
            task_id=f"fix-{uuid.uuid4().hex[:10]}",
            objective=objective,
            acceptance=(
                "Fix only the demonstrated failure.",
                "Return a replacement unified diff in <CEO_PATCH> tags.",
                "Do not add recovery, retries or unrelated refactors unless the failure specifically requires it.",
            ),
            context=context,
            programming=True,
        )


def load_recipe(path: str | Path) -> dict[str, Any]:
    row = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(row, dict):
        raise ValueError("recipe must be an object")
    required = {"provider", "url", "input_selectors", "send_selectors", "response_selectors"}
    missing = sorted(required - set(row))
    if missing:
        raise ValueError(f"recipe missing: {', '.join(missing)}")
    return row
