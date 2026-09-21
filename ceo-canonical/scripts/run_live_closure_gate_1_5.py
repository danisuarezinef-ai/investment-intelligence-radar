from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.ai_worker import AIWorkerProvider
from ceo_core.contracts import WorkerRequest, WorkUnit
from ceo_core.conversation_controller import ConversationController
from ceo_core.goal_engine import GoalEngine
from ceo_core.models import ProjectState, Task, TaskStatus
from ceo_core.provider_secrets import resolve_provider_secret
from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport
from ceo_core.providers.openai_responses import OpenAIResponsesTransport

REPORT = ROOT / "reports" / "CLOSURE_1_5_LIVE_REPORT.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def provider():
    openai = resolve_provider_secret("openai")
    if openai:
        return AIWorkerProvider(OpenAIResponsesTransport(api_key=openai))
    gemini = resolve_provider_secret("gemini")
    if gemini:
        return AIWorkerProvider(GeminiInteractionsTransport(api_key=gemini))
    return None


async def main() -> int:
    report = {
        "generated_at_utc": now(),
        "gate": "CEO closure 1-5 / live conversation controller",
        "status": "NOT VERIFIED",
        "marker": None,
        "reason": "No configured OpenAI/Gemini API credential was available.",
    }
    worker = provider()
    if worker is None:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print("NOT VERIFIED: configure an API in CEO de IAs, then rerun this gate.")
        return 2

    goal = GoalEngine().lock(
        "Validate autonomous two-turn continuation",
        success_definition="The same provider conversation completes two turns without human continue.",
        constraints=["Do not perform external actions"],
    )
    state = ProjectState(goal=goal.objective)
    GoalEngine().apply(state, goal)
    task = Task(
        title="Live two-turn controller probe",
        description=(
            "This is a bounded validation. On the FIRST turn, return a short token beginning GATE- and "
            "end with CEO_RESULT status=continue, next_instruction='finish the validation using the same token'. "
            "On the SECOND turn, repeat the same token and end with status=complete. Do not ask the human anything."
        ),
        status=TaskStatus.READY,
        required_capabilities=["general"],
    )
    state.tasks = {task.id: task}
    state.root_task_ids = [task.id]
    controller = ConversationController(max_turns=4)

    transcript = []
    try:
        for turn in range(2):
            request = WorkerRequest(
                project_id=state.id,
                goal=goal,
                work_unit=WorkUnit.from_task(task),
                conversation_id=task.conversation_id,
                turn_index=task.conversation_turns,
                instruction=task.metadata.pop("next_instruction", None),
                context={"validation_gate": "closure-1-5", "expected_turn": turn + 1},
            )
            result = await worker.execute(request)
            decision = controller.decide(state, task, result)
            transcript.append({
                "turn": turn + 1,
                "provider": result.provider,
                "success": result.success,
                "conversation_id_present": bool(result.conversation_id),
                "decision": decision.action.value,
                "requires_user": decision.requires_user,
                "error": result.error,
            })
            controller.apply(state, task, result, decision)
            if turn == 0 and decision.action.value != "continue":
                raise RuntimeError(f"first turn returned {decision.action.value}, expected continue")
            if decision.requires_user:
                raise RuntimeError("controller required a user intervention")
        if task.status != TaskStatus.COMPLETE or task.conversation_turns != 2 or not task.conversation_id:
            raise RuntimeError("two-turn conversation did not close cleanly")
        report.update({
            "status": "VERIFIED",
            "marker": "CEO_LIVE_VALIDATED",
            "reason": "Two live provider turns completed through ConversationController without manual continuation.",
            "provider": worker.name,
            "conversation_turns": task.conversation_turns,
            "human_interventions_avoided": state.human_interventions_avoided,
            "transcript": transcript,
        })
        code = 0
    except Exception as exc:  # validation must fail closed
        report.update({"status": "FAILED", "reason": f"{type(exc).__name__}: {exc}", "transcript": transcript})
        code = 1

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{report['status']}: {report['reason']}")
    if report.get("marker"):
        print(report["marker"])
    return code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
