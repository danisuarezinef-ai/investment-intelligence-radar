from __future__ import annotations

import os
from typing import Any

import httpx

from ceo_core.ai_worker import AITransport, AITransportRequest, AITransportResponse
from ceo_core.contracts import ProviderHealth, WorkerKind


class OpenAIResponsesTransport(AITransport):
    """OpenAI Responses API transport with server-side multi-turn continuation."""

    name = "openai-responses"
    kind = WorkerKind.API

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("CEO_OPENAI_MODEL", "gpt-5.6-luna")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def send(self, request: AITransportRequest) -> AITransportResponse:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        payload: dict[str, Any] = {
            "model": self.model,
            "input": request.prompt,
            "store": True,
        }
        if request.conversation_id:
            payload["previous_response_id"] = request.conversation_id

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        finally:
            if owns_client:
                await client.aclose()

        return AITransportResponse(
            text=self._extract_text(data),
            conversation_id=data.get("id"),
            usage=data.get("usage") or {},
            metadata={"model": data.get("model", self.model), "status": data.get("status")},
        )

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        # Some SDK representations expose output_text; raw REST is safely handled via output[].
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        texts: list[str] = []
        for item in data.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    texts.append(content["text"])
        return "\n".join(texts).strip()

    async def probe_live(self) -> dict[str, Any]:
        """Authenticated provider proof. A configured key alone is not validation."""
        if not self.api_key:
            return {"ok": False, "reason": "api_key_not_configured", "model": self.model}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=min(self.timeout_seconds, 30.0))
        try:
            response = await client.get(
                f"{self.base_url}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            if response.status_code >= 400:
                return {"ok": False, "status_code": response.status_code, "reason": "authenticated_probe_failed", "model": self.model}
            data = response.json()
            return {"ok": True, "status_code": response.status_code, "model": self.model, "models_visible": len(data.get("data") or [])}
        finally:
            if owns_client:
                await client.aclose()

    async def healthcheck(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(
                provider=self.name,
                available=False,
                detail="OPENAI_API_KEY is not configured; transport code is installed but live use is unavailable.",
                metadata={"model": self.model},
            )
        return ProviderHealth(provider=self.name, available=True, detail="API key configured; authenticated live probe not implied.", metadata={"model": self.model})
