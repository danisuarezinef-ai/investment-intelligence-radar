from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
import json

from .contracts import ProviderHealth, WorkerKind, WorkerProvider, WorkerRequest, WorkerResult


@dataclass(slots=True, frozen=True)
class AITransportRequest:
    """Provider-agnostic message sent by :class:`AIWorkerProvider` to an AI transport.

    ``conversation_id`` is intentionally opaque.  An API transport may map it to a
    previous-response id, a browser transport to a chat URL/id, and a local model to
    an in-memory/session key.  CEO Core never interprets it.
    """

    prompt: str
    conversation_id: str | None = None
    turn_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AITransportResponse:
    """Normalized response returned by an AI transport."""

    text: str
    conversation_id: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    artifacts: list[str] = field(default_factory=list)
    suggested_followups: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class AITransport(ABC):
    """Smallest possible boundary between CEO and a concrete AI execution surface."""

    name: str = "ai-transport"
    kind: WorkerKind = WorkerKind.API

    @abstractmethod
    async def send(self, request: AITransportRequest) -> AITransportResponse:
        raise NotImplementedError

    async def healthcheck(self) -> ProviderHealth:
        return ProviderHealth(provider=self.name, available=True)


class AIPromptBuilder:
    """Builds deterministic first-turn and continuation prompts.

    The worker is responsible for supplying enough context for one chat to operate
    without repeatedly asking the user to drive it.  Provider-specific prompting is
    deliberately kept out of the scheduler.
    """

    def build(self, request: WorkerRequest) -> str:
        if request.conversation_id:
            return self._continuation_prompt(request)
        return self._initial_prompt(request)

    @staticmethod
    def _section(title: str, values: list[str]) -> str:
        if not values:
            return f"{title}: none specified"
        return title + ":\n" + "\n".join(f"- {value}" for value in values)

    def _initial_prompt(self, request: WorkerRequest) -> str:
        from .self_hosting_runtime import CEOAIContract
        unit = request.work_unit
        contract = CEOAIContract().build(request)
        contract_json = json.dumps({
            "schema_version": contract.schema_version, "project_id": contract.project_id,
            "role": contract.role, "objective": contract.objective,
            "success_definition": contract.success_definition, "constraints": contract.constraints,
            "forbidden_actions": contract.forbidden_actions, "work_unit": contract.work_unit,
            "definition_of_done": contract.definition_of_done, "artifact_inputs": contract.artifact_inputs,
            "response_contract": contract.response_contract,
        }, ensure_ascii=False, default=str)
        instruction = request.instruction or (
            "Complete this work unit autonomously. Do not ask the user to say 'continue'. "
            "If the work can be completed now, produce the substantive result now."
        )
        return "\n\n".join(
            [
                "You are one execution worker inside CEO de IAs, an autonomous project orchestrator.",
                f"CEO_WORKER_CONTRACT_JSON:\n{contract_json}",
                f"PROJECT GOAL:\n{request.goal.objective}",
                f"GOAL DEFINITION:\n{request.goal.definition or request.goal.objective}",
                f"SUCCESS DEFINITION:\n{request.goal.success_definition or 'Complete the locked goal to the stated criteria.'}",
                self._section("PROJECT DELIVERABLES", request.goal.deliverables),
                self._section("PROJECT CONSTRAINTS", request.goal.constraints),
                self._section("FORBIDDEN ACTIONS", request.goal.forbidden_actions),
                f"DEADLINE: {request.goal.deadline or 'none'} · URGENCY: {request.goal.urgency}/100 · BUDGET LIMIT: {request.goal.budget_limit if request.goal.budget_limit is not None else 'none'}",
                f"WORK UNIT:\n{unit.title}",
                f"WORK UNIT DESCRIPTION:\n{unit.description or unit.title}",
                self._section("ACCEPTANCE CRITERIA", unit.acceptance_criteria),
                f"PRIORITY: {unit.priority}/100",
                f"RELEVANT PROJECT CONTEXT:\n{json.dumps(request.context, ensure_ascii=False, default=str)[:12000]}",
                f"CURRENT INSTRUCTION:\n{instruction}",
                (
                    "OPERATING RULES:\n"
                    "- Stay focused on this work unit and the locked project goal.\n"
                    "- Make a best effort with the information and tools available to you.\n"
                    "- Do not invent completed checks, sources, tests, or evidence.\n"
                    "- State unresolved blockers explicitly.\n"
                    "- Return work that another controller can evaluate and integrate.\n"
                    "- If a requested deliverable is a workspace file, use write_files with a RELATIVE path and complete content. "
                    "CEO will perform the guarded local write; never claim a file exists merely because you described it.\n"
                    "- When auditing completion, use evidence_refs only from the explicit goal_audit_evidence_candidates supplied in context.\n"
                    "- End EVERY turn with exactly one machine-readable control footer:\n"
                    "<CEO_RESULT>{\"status\":\"complete|continue|correct|deepen|spawn|review|escalate|retry\","
                    "\"reason\":\"...\",\"next_instruction\":null,\"followups\":[],"
                    "\"confidence\":0.0,\"requires_user\":false,\"evidence_refs\":[],"
                    "\"write_files\":[{\"path\":\"relative/file.md\",\"content\":\"complete file content\"}]}</CEO_RESULT>\n"
                    "- Use write_files=[] when no file should be written.\n"
                    "- Use status=continue/deepen/correct when more turns in THIS SAME chat are needed; do not ask the human to say continue."
                ),
            ]
        )

    def _continuation_prompt(self, request: WorkerRequest) -> str:
        instruction = request.instruction or (
            "Continue the same work unit from the existing conversation context. "
            "Resolve what remains and return the updated substantive result."
        )
        return "\n\n".join(
            [
                f"CONTINUE WORK UNIT: {request.work_unit.title}",
                f"TURN: {request.turn_index + 1}",
                f"INSTRUCTION:\n{instruction}",
                (
                    "Use the existing conversation context. Do not restart the task, do not ask "
                    "for permission to continue, and do not claim work you have not actually done.\n"
                    "End the turn with one <CEO_RESULT>{...}</CEO_RESULT> control footer using the full schema "
                    "including evidence_refs and write_files. File writes must use relative workspace paths. "
                    "If more work is needed in this chat, set status to continue/deepen/correct and provide next_instruction."
                ),
            ]
        )


class AIWorkerProvider(WorkerProvider):
    """Reusable real AI worker sitting behind CEO's stable WorkerProvider contract.

    It handles prompt construction, continuation identifiers, error normalization and
    provider-neutral result mapping.  Concrete service connections are supplied by an
    ``AITransport`` and can therefore be swapped without changing CEO Core.
    """

    capabilities = frozenset({"general", "chat", "reasoning", "analysis", "writing", "coding"})

    def __init__(
        self,
        transport: AITransport,
        *,
        prompt_builder: AIPromptBuilder | None = None,
        capabilities: frozenset[str] | None = None,
    ) -> None:
        self.transport = transport
        self.prompt_builder = prompt_builder or AIPromptBuilder()
        self.name = transport.name
        self.kind = transport.kind
        if capabilities is not None:
            self.capabilities = capabilities

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        transport_request = AITransportRequest(
            prompt=self.prompt_builder.build(request),
            conversation_id=request.conversation_id,
            turn_index=request.turn_index,
            metadata={
                "project_id": request.project_id,
                "work_unit_id": request.work_unit.id,
                **request.context,
            },
        )
        try:
            response = await self.transport.send(transport_request)
        except Exception as exc:  # noqa: BLE001 - worker isolates service errors for scheduler policy
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=False,
                conversation_id=request.conversation_id,
                error=f"{type(exc).__name__}: {exc}",
                metadata={"turn_index": request.turn_index},
            )

        conversation_id = response.conversation_id or request.conversation_id
        if request.conversation_id and response.conversation_id:
            # A transport may return a new response-id on every turn (e.g. chained API
            # responses).  That is valid: CEO persists the newest opaque identifier.
            conversation_id = response.conversation_id

        return WorkerResult(
            provider=self.name,
            kind=self.kind,
            success=True,
            text=response.text,
            conversation_id=conversation_id,
            usage=dict(response.usage),
            artifacts=list(response.artifacts),
            suggested_followups=list(response.suggested_followups),
            metadata={"turn_index": request.turn_index, **response.metadata},
        )

    async def healthcheck(self) -> ProviderHealth:
        return await self.transport.healthcheck()
