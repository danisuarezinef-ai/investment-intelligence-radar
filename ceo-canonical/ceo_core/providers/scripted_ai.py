from __future__ import annotations

from collections import defaultdict, deque
from uuid import uuid4

from ceo_core.ai_worker import AITransport, AITransportRequest, AITransportResponse
from ceo_core.contracts import WorkerKind


class ScriptedAITransport(AITransport):
    """Deterministic AI transport used for development/integration tests.

    This is not the production provider connection.  It behaves like a multi-turn AI
    service so the real AIWorker lifecycle can be tested before task 3 connects the
    first external provider.
    """

    name = "scripted-ai"
    kind = WorkerKind.MOCK

    def __init__(self, replies: list[str] | None = None) -> None:
        self._default_replies = deque(replies or ["Work unit completed."])
        self._sessions: dict[str, list[AITransportRequest]] = defaultdict(list)
        self.requests: list[AITransportRequest] = []

    async def send(self, request: AITransportRequest) -> AITransportResponse:
        conversation_id = request.conversation_id or f"scripted-{uuid4().hex}"
        self.requests.append(request)
        self._sessions[conversation_id].append(request)
        text = self._default_replies.popleft() if self._default_replies else "Work unit completed."
        return AITransportResponse(
            text=text,
            conversation_id=conversation_id,
            usage={"turns": len(self._sessions[conversation_id])},
            metadata={"scripted": True},
        )

    def session_turns(self, conversation_id: str) -> list[AITransportRequest]:
        return list(self._sessions.get(conversation_id, []))
