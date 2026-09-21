from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from typing import Any, Awaitable, Callable

import httpx

from ceo_core.ai_worker import AITransport, AITransportRequest, AITransportResponse
from ceo_core.contracts import ProviderHealth, WorkerKind


class GeminiInteractionsTransport(AITransport):
    """Resilient Gemini ``generateContent`` transport.

    Design goals for the Windows RC:
    - never advertise Gemini as healthy merely because a key exists;
    - validate live generation before enabling execution;
    - retry bounded transient failures (network, timeout, 429, 5xx);
    - fall back across already-visible models without buying/enabling anything;
    - keep multi-turn history intact across transient failures/reconnection;
    - never leak the API key into errors or metadata.
    """

    name = "gemini-interactions"
    kind = WorkerKind.API
    TRANSIENT_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
    MODEL_SCOPED_STATUS = frozenset({400, 403, 404, 429})
    # Current stable text models, ordered for CEO's low-cost/high-throughput use case.
    # The order deliberately avoids Gemini 2.5 Flash-Lite first because Google now
    # returns 404 for new users/projects even though it can still be visible in listModels.
    PREFERRED_STABLE_MODELS = (
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.1-flash-lite",
    )
    KNOWN_UNAVAILABLE_MODELS = frozenset({"gemini-2.5-flash", "gemini-2.5-flash-lite"})
    PROBE_MODEL_LIMIT = 2

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
        max_attempts_per_model: int = 3,
        max_models: int = 12,
        backoff_base_seconds: float = 0.35,
        max_backoff_seconds: float = 8.0,
        sleep: Callable[[float], Awaitable[Any]] | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = (model or os.getenv("CEO_GEMINI_MODEL") or "auto").replace("models/", "", 1)
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self._client = client
        self.max_attempts_per_model = max(1, int(max_attempts_per_model))
        self.max_models = max(1, int(max_models))
        self.backoff_base_seconds = max(0.0, float(backoff_base_seconds))
        self.max_backoff_seconds = max(0.0, float(max_backoff_seconds))
        self._sleep = sleep or asyncio.sleep
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._discovered_models: list[str] | None = None
        self._last_probe: dict[str, Any] | None = None
        self._last_success_monotonic: float | None = None

    @classmethod
    def _model_score(cls, name: str) -> tuple[int, int, str]:
        low = name.lower()
        bad = any(x in low for x in ("preview", "exp", "image", "tts", "live", "embedding"))
        try:
            preferred = cls.PREFERRED_STABLE_MODELS.index(low)
        except ValueError:
            preferred = 999
        if preferred != 999:
            return (0, preferred, low)
        if not bad and low.startswith("gemini-3") and "flash" in low:
            return (1, 0, low)
        if not bad and "flash" in low:
            return (2, 0, low)
        return (3 if not bad else 4, 0, low)

    @staticmethod
    def _parts(text: str) -> list[dict[str, str]]:
        return [{"text": text}]

    def _redact(self, value: Any) -> str:
        text = str(value)
        if self.api_key:
            text = text.replace(self.api_key, "<redacted-api-key>")
        return text

    @staticmethod
    def _retry_after_seconds(response: httpx.Response | None) -> float | None:
        if response is None:
            return None
        raw = (response.headers.get("retry-after") or "").strip()
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            return None

    async def _bounded_sleep(self, attempt: int, response: httpx.Response | None = None) -> None:
        hinted = self._retry_after_seconds(response)
        if hinted is None:
            hinted = self.backoff_base_seconds * (2 ** max(0, attempt - 1))
        await self._sleep(min(self.max_backoff_seconds, max(0.0, hinted)))

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        attempts: int | None = None,
    ) -> tuple[httpx.Response, dict[str, Any]]:
        max_attempts = max(1, int(attempts or self.max_attempts_per_model))
        last_exc: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            response: httpx.Response | None = None
            try:
                response = await client.request(method, url, headers=headers, params=params, json=payload)
                if response.status_code in self.TRANSIENT_STATUS and attempt < max_attempts:
                    await self._bounded_sleep(attempt, response)
                    continue
                response.raise_for_status()
                try:
                    data = response.json()
                except (json.JSONDecodeError, ValueError) as exc:
                    if attempt < max_attempts:
                        await self._bounded_sleep(attempt, response)
                        continue
                    raise RuntimeError("Gemini devolvió JSON inválido tras reintentos") from exc
                if not isinstance(data, dict):
                    raise RuntimeError("Gemini devolvió una respuesta JSON no válida")
                return response, data
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError, httpx.ReadError) as exc:
                last_exc = exc
                if attempt < max_attempts:
                    await self._bounded_sleep(attempt, response)
                    continue
                raise RuntimeError(f"Gemini temporalmente inaccesible: {type(exc).__name__}") from exc
            except httpx.HTTPStatusError:
                raise
        raise RuntimeError(f"Gemini no respondió: {type(last_exc).__name__ if last_exc else 'unknown'}")

    async def _discover_models(self, client: httpx.AsyncClient, *, force: bool = False) -> list[str]:
        if self._discovered_models is not None and not force:
            return list(self._discovered_models)
        response, data = await self._request_json(
            client,
            "GET",
            f"{self.base_url}/models",
            headers={"x-goog-api-key": self.api_key or ""},
            params={"pageSize": 100},
        )
        _ = response
        rows = data.get("models") or []
        candidates: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            methods = row.get("supportedGenerationMethods") or []
            name = str(row.get("name") or "")
            if "generateContent" not in methods or not name:
                continue
            short_name = name.removeprefix("models/")
            if short_name in self.KNOWN_UNAVAILABLE_MODELS:
                continue
            candidates.append(short_name)

        # Stable current-generation models are ranked before legacy Flash-Lite
        # names that may remain visible but unavailable to new users.
        candidates = sorted(dict.fromkeys(candidates), key=self._model_score)
        self._discovered_models = candidates
        return list(candidates)

    async def _candidate_models(self, client: httpx.AsyncClient) -> list[str]:
        discovered = await self._discover_models(client)
        if self.model and self.model != "auto":
            return [self.model] + [m for m in discovered if m != self.model]
        return discovered

    async def _generate(
        self,
        client: httpx.AsyncClient,
        *,
        model: str,
        contents: list[dict[str, Any]],
        max_output_tokens: int = 512,
        attempts: int | None = None,
    ) -> tuple[dict[str, Any], httpx.Response]:
        response, data = await self._request_json(
            client,
            "POST",
            f"{self.base_url}/models/{model}:generateContent",
            headers={"x-goog-api-key": self.api_key or "", "Content-Type": "application/json"},
            payload={
                "contents": contents,
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": int(max_output_tokens)},
            },
            attempts=attempts,
        )
        return data, response

    async def send(self, request: AITransportRequest) -> AITransportResponse:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        conversation_id = request.conversation_id or f"gemini-local-{uuid.uuid4().hex}"
        # Snapshot history. It is committed only after a successful model response.
        history = list(self._history.get(conversation_id, []))
        contents = history + [{"role": "user", "parts": self._parts(request.prompt)}]
        errors: list[str] = []
        try:
            models = await self._candidate_models(client)
            if not models:
                raise RuntimeError("No Gemini model supporting generateContent is visible for this API key")
            # Keep the historical twelve-model fallback ceiling while allowing
            # tests/configuration to choose an even smaller bound.
            models_to_try = models[:12]
            for model in models_to_try[: self.max_models]:
                try:
                    data, response = await self._generate(client, model=model, contents=contents)
                    text = self._extract_text(data)
                    if not text:
                        errors.append(f"{model}: empty model response")
                        continue
                    model_content = {"role": "model", "parts": self._parts(text)}
                    self._history[conversation_id] = contents + [model_content]
                    self.model = model
                    self._last_success_monotonic = time.monotonic()
                    self._last_probe = {
                        "ok": True,
                        "status": response.status_code,
                        "provider": self.name,
                        "model": model,
                        "verified_generation": True,
                        "verified_at_monotonic": self._last_success_monotonic,
                    }
                    return AITransportResponse(
                        text=text,
                        conversation_id=conversation_id,
                        usage=data.get("usageMetadata") or {},
                        metadata={"model": model, "status": "ok", "transport": "generateContent", "live_verified": True},
                    )
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    body = self._redact(exc.response.text[:500])
                    errors.append(f"{model}: HTTP {status} {body}")
                    if status == 401:
                        break
                    if status in self.MODEL_SCOPED_STATUS or status in self.TRANSIENT_STATUS:
                        continue
                    break
                except Exception as exc:  # bounded retries already happened inside _request_json
                    errors.append(f"{model}: {self._redact(type(exc).__name__ + ': ' + str(exc))}")
                    continue
            detail = " | ".join(errors[-6:]) if errors else "no detailed provider error"
            raise RuntimeError(f"Gemini generation failed across visible models: {detail}")
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        texts: list[str] = []
        for candidate in data.get("candidates") or []:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content") or {}
            for part in content.get("parts") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])
        return "\n".join(texts).strip()

    async def probe_live(self) -> dict[str, Any]:
        """Prove *real generation*, not just key formatting/model listing."""
        if not self.api_key:
            self._last_probe = {"ok": False, "status": "NOT_VERIFIED", "detail": "GEMINI_API_KEY is not configured"}
            return dict(self._last_probe)
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=min(self.timeout_seconds, 30.0))
        errors: list[str] = []
        try:
            models = await self._candidate_models(client)
            if not models:
                self._last_probe = {"ok": False, "status": "NO_GENERATION_MODEL", "detail": "No generateContent model visible", "authenticated": True, "models_visible": 0}
                return dict(self._last_probe)
            statuses: list[int] = []
            for model in models[: min(self.PROBE_MODEL_LIMIT, self.max_models)]:
                try:
                    data, response = await self._generate(
                        client,
                        model=model,
                        contents=[{"role": "user", "parts": self._parts("Reply exactly with OK.")}],
                        max_output_tokens=8,
                        attempts=1,
                    )
                    text = self._extract_text(data)
                    if not text:
                        errors.append(f"{model}: empty probe response")
                        continue
                    self.model = model
                    now = time.monotonic()
                    self._last_success_monotonic = now
                    self._last_probe = {
                        "ok": True,
                        "status": response.status_code,
                        "provider": self.name,
                        "models_visible": len(models),
                        "model": model,
                        "verified_generation": True,
                        "authenticated": True,
                        "verified_at_monotonic": now,
                    }
                    return dict(self._last_probe)
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    statuses.append(status)
                    errors.append(f"{model}: HTTP {status} {self._redact(exc.response.text[:300])}")
                    if status == 401:
                        break
                    continue
                except Exception as exc:
                    errors.append(f"{model}: {self._redact(type(exc).__name__ + ': ' + str(exc))}")
                    continue
            if statuses and all(code == 429 for code in statuses):
                probe_status = "QUOTA_EXHAUSTED"
            elif 429 in statuses:
                probe_status = "GENERATION_UNAVAILABLE_WITH_QUOTA_LIMIT"
            elif statuses and all(code == 404 for code in statuses):
                probe_status = "MODEL_UNAVAILABLE"
            else:
                probe_status = "GENERATION_UNAVAILABLE"
            self._last_probe = {
                "ok": False,
                "status": probe_status,
                "detail": " | ".join(errors[-8:]) or "Gemini generation probe failed",
                "models_visible": len(models),
                "models_tested": min(len(models), min(self.PROBE_MODEL_LIMIT, self.max_models)),
                "authenticated": True,
            }
            return dict(self._last_probe)
        except httpx.HTTPStatusError as exc:
            self._last_probe = {
                "ok": False,
                "status": exc.response.status_code,
                "detail": self._redact(exc.response.text[:500]),
                "authenticated": False if exc.response.status_code in {400, 401} else None,
            }
            return dict(self._last_probe)
        except Exception as exc:
            self._last_probe = {
                "ok": False,
                "status": "ERROR",
                "detail": self._redact(f"{type(exc).__name__}: {exc}"),
                "authenticated": None,
            }
            return dict(self._last_probe)
        finally:
            if owns_client:
                await client.aclose()

    async def healthcheck(self) -> ProviderHealth:
        if not self.api_key:
            return ProviderHealth(
                provider=self.name,
                available=False,
                detail="GEMINI_API_KEY is not configured; live use is unavailable.",
                metadata={"model": self.model, "live_verified": False},
            )
        probe = self._last_probe or {}
        verified_at = probe.get("verified_at_monotonic")
        fresh = bool(probe.get("ok") and verified_at is not None and (time.monotonic() - float(verified_at)) <= 300.0)
        if not fresh:
            return ProviderHealth(
                provider=self.name,
                available=False,
                detail="API key configured but real generation has not been live-verified recently.",
                metadata={"model": self.model, "live_verified": False},
            )
        return ProviderHealth(
            provider=self.name,
            available=True,
            detail="Gemini real generation verified.",
            metadata={"model": self.model, "live_verified": True},
        )
