from __future__ import annotations

import asyncio
import html
import ipaddress
import json
import re
import socket
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol


@dataclass(frozen=True)
class FieldGoalSpec:
    goal_id: str = "FIELD-MVP-01"
    objective: str = (
        "Investiga qué es el entrenamiento en Zona 2, cuáles son sus principales "
        "beneficios y cuáles son sus limitaciones, utilizando 5 fuentes fiables "
        "diferentes. Genera FIELD_MVP_01.md, de 700–1.000 palabras, con explicación "
        "breve, beneficios, limitaciones, conclusión y las 5 fuentes identificables."
    )
    output_name: str = "FIELD_MVP_01.md"
    min_words: int = 700
    max_words: int = 1000
    min_sources: int = 5
    required_headings: tuple[str, ...] = (
        "## Qué es el entrenamiento en Zona 2",
        "## Beneficios",
        "## Limitaciones",
        "## Conclusión",
        "## Fuentes",
    )


DEFAULT_SPEC = FieldGoalSpec()


class TextProvider(Protocol):
    name: str

    async def generate(self, prompt: str, *, max_output_tokens: int) -> str: ...


ProviderFactory = Callable[[], TextProvider]
SourceProbe = Callable[[str], Awaitable[dict[str, Any]]]


@dataclass
class StepRecord:
    name: str
    status: str = "pending"
    attempts: int = 0
    detail: str = ""


@dataclass
class FieldSession:
    session_id: str
    goal_id: str
    objective: str
    output_path: str
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"
    stage: str = "starting"
    delivery_pass: bool | None = None
    failure_reason: str = ""
    verifier: dict[str, Any] = field(default_factory=dict)
    deterministic_checks: dict[str, Any] = field(default_factory=dict)
    source_checks: list[dict[str, Any]] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal_id": self.goal_id,
            "objective": self.objective,
            "output_path": self.output_path,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "stage": self.stage,
            "delivery_pass": self.delivery_pass,
            "failure_reason": self.failure_reason,
            "verifier": self.verifier,
            "deterministic_checks": self.deterministic_checks,
            "source_checks": self.source_checks,
            "steps": [vars(x) for x in self.steps],
        }


class SingleGeminiProvider:
    """One-provider adapter for MVP_FIELD.

    It intentionally bypasses CEO's router/scheduler and uses only one Gemini model.
    Internal request retries are disabled. The runner itself allows at most one retry
    after an initial failed call.
    """

    name = "gemini-interactions"

    def __init__(self, api_key: str, *, model: str = "auto", timeout_seconds: float = 90.0) -> None:
        if not api_key:
            raise ValueError("Gemini API key required")
        from ceo_core.providers.gemini_interactions import GeminiInteractionsTransport

        self._transport = GeminiInteractionsTransport(
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_attempts_per_model=1,
            max_models=1,
            backoff_base_seconds=0.0,
            max_backoff_seconds=0.0,
        )

    async def generate(self, prompt: str, *, max_output_tokens: int) -> str:
        transport = self._transport
        owns_client = transport._client is None
        client = transport._client or transport._make_client(transport.timeout_seconds)
        try:
            models = await transport._candidate_models(client)
            if not models:
                raise RuntimeError("Gemini no expone un modelo generateContent utilizable")
            model = models[0]
            data, _response = await transport._generate(
                client,
                model=model,
                contents=[{"role": "user", "parts": transport._parts(prompt)}],
                max_output_tokens=int(max_output_tokens),
                attempts=1,
            )
            text = transport._extract_text(data)
            if not text.strip():
                raise RuntimeError("Gemini devolvió una respuesta vacía")
            transport.model = model
            return text.strip()
        finally:
            if owns_client:
                await client.aclose()


class MVPFieldRunner:
    """Minimal, intentionally boring happy-path executor.

    There is no scheduler, recovery supervisor, continuity audit, storm breaker,
    provider router, self-development loop or updater. The only automatic retry is
    one second attempt of the same bounded provider call.
    """

    NORMAL_STEPS = (
        "research",
        "draft",
        "write",
        "independent_verify",
    )
    OPTIONAL_STEPS = (
        "single_correction",
        "final_verify",
    )

    def __init__(
        self,
        *,
        provider_factory: ProviderFactory,
        results_root: str | Path,
        spec: FieldGoalSpec = DEFAULT_SPEC,
        source_probe: SourceProbe | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.results_root = Path(results_root).resolve()
        self.spec = spec
        self.source_probe = source_probe or self._probe_public_source
        self.session: FieldSession | None = None
        self._status_path = self.results_root / "MVP_FIELD_STATUS.json"

    def _persist(self) -> None:
        if self.session is None:
            return
        self.results_root.mkdir(parents=True, exist_ok=True)
        self._status_path.write_text(
            json.dumps(self.session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def snapshot(self) -> dict[str, Any]:
        if self.session is None:
            return {
                "mode": "MVP_FIELD",
                "goal_id": self.spec.goal_id,
                "goal": self.spec.objective,
                "status": "idle",
                "stage": "idle",
                "delivery_pass": None,
                "output_path": str(self.results_root / self.spec.output_name),
                "steps": [],
            }
        return self.session.to_dict() | {"mode": "MVP_FIELD"}

    def _set_step(self, name: str, status: str, *, attempts: int | None = None, detail: str = "") -> None:
        if self.session is None:
            return
        row = next((x for x in self.session.steps if x.name == name), None)
        if row is None:
            row = StepRecord(name=name)
            self.session.steps.append(row)
        row.status = status
        if attempts is not None:
            row.attempts = attempts
        if detail:
            row.detail = detail[:1200]
        self.session.stage = name
        self._persist()

    async def _provider_call(self, phase: str, prompt: str, *, max_output_tokens: int) -> str:
        last: Exception | None = None
        for attempt in (1, 2):
            self._set_step(phase, "running", attempts=attempt)
            try:
                provider = self.provider_factory()
                text = await provider.generate(prompt, max_output_tokens=max_output_tokens)
                if not text.strip():
                    raise RuntimeError("respuesta vacía")
                self._set_step(phase, "complete", attempts=attempt)
                return text.strip()
            except Exception as exc:  # one retry only
                last = exc
                self._set_step(phase, "retry" if attempt == 1 else "failed", attempts=attempt, detail=f"{type(exc).__name__}: {exc}")
                if attempt == 1:
                    await asyncio.sleep(1.0)
        assert last is not None
        raise RuntimeError(f"{phase} falló tras un único retry: {type(last).__name__}: {last}") from last

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        value = text.strip()
        if value.startswith("```"):
            value = re.sub(r"^\s*```(?:markdown|md|json|text)?\s*", "", value, count=1, flags=re.I)
            value = re.sub(r"\s*```\s*$", "", value, count=1)
        return value.strip()

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        value = MVPFieldRunner._strip_code_fence(text)
        try:
            row = json.loads(value)
            return row if isinstance(row, dict) else {}
        except Exception:
            pass
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            try:
                row = json.loads(value[start : end + 1])
                return row if isinstance(row, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\b[\wÁÉÍÓÚÜÑáéíóúüñ'-]+\b", text, flags=re.UNICODE))

    @staticmethod
    def _extract_urls(text: str) -> list[str]:
        urls = re.findall(r"https?://[^\s<>()\[\]{}]+", text, flags=re.I)
        cleaned = []
        for raw in urls:
            url = raw.rstrip(".,;:!?)'\"")
            if url not in cleaned:
                cleaned.append(url)
        return cleaned

    def _deterministic_checks(self, text: str) -> dict[str, Any]:
        words = self._word_count(text)
        headings = {h: (h.lower() in text.lower()) for h in self.spec.required_headings}
        urls = self._extract_urls(text)
        return {
            "nonempty": bool(text.strip()),
            "word_count": words,
            "word_count_ok": self.spec.min_words <= words <= self.spec.max_words,
            "headings": headings,
            "headings_ok": all(headings.values()),
            "source_url_count": len(urls),
            "source_count_ok": len(urls) >= self.spec.min_sources,
            "urls": urls[:20],
        }

    @staticmethod
    def _public_host(url: str) -> tuple[bool, str]:
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                return False, "invalid_scheme_or_host"
            if parsed.username or parsed.password:
                return False, "userinfo_not_allowed"
            host = parsed.hostname
            if host.lower() in {"localhost", "localhost.localdomain"}:
                return False, "localhost_not_allowed"
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
            if not infos:
                return False, "dns_empty"
            for info in infos:
                ip = ipaddress.ip_address(info[4][0])
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_unspecified or ip.is_reserved:
                    return False, "non_public_ip"
            return True, "ok"
        except Exception as exc:
            return False, f"dns_or_parse_error:{type(exc).__name__}"

    @classmethod
    async def _probe_public_source(cls, url: str) -> dict[str, Any]:
        def _probe() -> dict[str, Any]:
            allowed, reason = cls._public_host(url)
            if not allowed:
                return {"url": url, "reachable": False, "status": None, "title": "", "reason": reason}
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 CEO-MVP-FIELD/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/pdf,text/plain;q=0.8,*/*;q=0.5",
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    body = response.read(32768)
                    ctype = str(response.headers.get("Content-Type") or "")
                title = ""
                if "html" in ctype.lower():
                    text = body.decode("utf-8", "replace")
                    m = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.I | re.S)
                    if m:
                        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()[:240]
                return {
                    "url": url,
                    "reachable": 200 <= status < 400,
                    "status": status,
                    "title": title,
                    "reason": "ok" if 200 <= status < 400 else "http_status",
                }
            except Exception as exc:
                return {
                    "url": url,
                    "reachable": False,
                    "status": getattr(exc, "code", None),
                    "title": "",
                    "reason": f"{type(exc).__name__}: {exc}"[:300],
                }

        return await asyncio.to_thread(_probe)

    async def _probe_sources(self, text: str) -> list[dict[str, Any]]:
        urls = self._extract_urls(text)[: max(self.spec.min_sources, 8)]
        checks = []
        for url in urls:
            checks.append(await self.source_probe(url))
        return checks

    def _research_prompt(self) -> str:
        return f"""MODO CEO MVP_FIELD. Realiza SOLO la fase de investigación de este objetivo:

{self.spec.objective}

Devuelve exclusivamente JSON válido con esta forma:
{{
  "notes": "síntesis factual extensa en español",
  "sources": [
    {{"title":"...", "publisher":"...", "year":"...", "url":"https://...", "relevance":"..."}}
  ]
}}

Requisitos:
- exactamente una investigación focalizada, sin planes ni auditorías;
- al menos {self.spec.min_sources} fuentes diferentes, fiables e identificables;
- cada fuente debe incluir URL pública completa;
- distingue beneficios razonablemente respaldados de limitaciones/incertidumbres;
- no inventes estudios, URLs ni comprobaciones;
- no escribas todavía el archivo final.
"""

    def _draft_prompt(self, research: dict[str, Any]) -> str:
        payload = json.dumps(research, ensure_ascii=False, indent=2)[:24000]
        headings = "\n".join(self.spec.required_headings)
        return f"""MODO CEO MVP_FIELD. Redacta el entregable final usando únicamente la investigación suministrada.

OBJETIVO:
{self.spec.objective}

INVESTIGACIÓN:
{payload}

Devuelve SOLO Markdown, sin bloque de código y sin comentarios externos.
El documento debe tener entre {self.spec.min_words} y {self.spec.max_words} palabras y usar exactamente estas secciones:
{headings}

En ## Fuentes incluye al menos {self.spec.min_sources} referencias diferentes con título, entidad/revista, año y URL completa.
No afirmes haber verificado una URL si no consta en la investigación. Sé preciso, útil y prudente con las limitaciones.
"""

    def _verifier_prompt(
        self,
        text: str,
        deterministic: dict[str, Any],
        source_checks: list[dict[str, Any]],
    ) -> str:
        return f"""Eres el verificador independiente y no has participado en la redacción.
Evalúa el entregable contra el objetivo y la evidencia técnica. No lo reescribas.

OBJETIVO:
{self.spec.objective}

ENTREGABLE:
{text[:30000]}

COMPROBACIONES DETERMINISTAS:
{json.dumps(deterministic, ensure_ascii=False, indent=2)}

SONDEO INDEPENDIENTE DE FUENTES:
{json.dumps(source_checks, ensure_ascii=False, indent=2)[:14000]}

Devuelve SOLO JSON válido:
{{
  "pass": true|false,
  "reasons": ["..."],
  "checks": {{
    "answers_goal": true|false,
    "benefits_balanced": true|false,
    "limitations_present": true|false,
    "sources_identifiable": true|false,
    "sources_plausibly_relevant": true|false,
    "no_obvious_fabrication": true|false
  }}
}}

PASS sólo si el archivo responde de forma sustantiva al objetivo, cumple el contrato estructural,
presenta beneficios y limitaciones de forma equilibrada y las fuentes son identificables y
plausiblemente pertinentes. Si hay duda material, usa pass=false.
"""

    def _correction_prompt(
        self,
        text: str,
        deterministic: dict[str, Any],
        verifier: dict[str, Any],
        research: dict[str, Any],
    ) -> str:
        return f"""MODO CEO MVP_FIELD. Esta es la ÚNICA corrección permitida.

OBJETIVO:
{self.spec.objective}

BORRADOR ACTUAL:
{text[:30000]}

FALLOS DETERMINISTAS:
{json.dumps(deterministic, ensure_ascii=False, indent=2)}

VERIFICADOR:
{json.dumps(verifier, ensure_ascii=False, indent=2)}

INVESTIGACIÓN ORIGINAL:
{json.dumps(research, ensure_ascii=False, indent=2)[:18000]}

Corrige sólo lo necesario. Devuelve SOLO el Markdown final completo.
Respeta {self.spec.min_words}-{self.spec.max_words} palabras, las cinco secciones requeridas
y al menos {self.spec.min_sources} fuentes identificables con URL. No añadas nuevas fuentes
que no estén en la investigación original.
"""

    async def _verify(self, text: str, *, phase: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
        deterministic = self._deterministic_checks(text)
        sources = await self._probe_sources(text)
        provider_json = self._extract_json(
            await self._provider_call(
                phase,
                self._verifier_prompt(text, deterministic, sources),
                max_output_tokens=1200,
            )
        )
        provider_checks = dict(provider_json.get("checks") or {}) if isinstance(provider_json, dict) else {}
        deterministic_pass = bool(
            deterministic.get("nonempty")
            and deterministic.get("word_count_ok")
            and deterministic.get("headings_ok")
            and deterministic.get("source_count_ok")
        )
        reachable = sum(1 for row in sources if row.get("reachable"))
        source_probe_pass = reachable >= min(self.spec.min_sources, max(3, self.spec.min_sources - 1))
        verifier_pass = bool(provider_json.get("pass")) if isinstance(provider_json, dict) else False
        combined = {
            "pass": bool(deterministic_pass and source_probe_pass and verifier_pass),
            "deterministic_pass": deterministic_pass,
            "source_probe_pass": source_probe_pass,
            "reachable_sources": reachable,
            "provider_pass": verifier_pass,
            "provider_reasons": list(provider_json.get("reasons") or []) if isinstance(provider_json, dict) else ["verifier_json_invalid"],
            "provider_checks": provider_checks,
        }
        return combined, deterministic, sources

    async def run(self) -> dict[str, Any]:
        self.results_root.mkdir(parents=True, exist_ok=True)
        output_path = self.results_root / self.spec.output_name
        run_root = self.results_root / "MVP_FIELD" / f"{self.spec.goal_id}-{uuid.uuid4().hex[:10]}"
        run_root.mkdir(parents=True, exist_ok=True)

        self.session = FieldSession(
            session_id=run_root.name,
            goal_id=self.spec.goal_id,
            objective=self.spec.objective,
            output_path=str(output_path),
            steps=[StepRecord(name=x) for x in self.NORMAL_STEPS],
        )
        self._persist()

        try:
            research_raw = await self._provider_call("research", self._research_prompt(), max_output_tokens=2800)
            research = self._extract_json(research_raw)
            sources = list(research.get("sources") or []) if isinstance(research, dict) else []
            if not research.get("notes") or len(sources) < self.spec.min_sources:
                raise RuntimeError("research no produjo notas y cinco fuentes estructuradas")
            (run_root / "research.json").write_text(
                json.dumps(research, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            draft = self._strip_code_fence(
                await self._provider_call("draft", self._draft_prompt(research), max_output_tokens=4200)
            )
            self._set_step("write", "running", attempts=1)
            output_path.write_text(draft.rstrip() + "\n", encoding="utf-8")
            (run_root / self.spec.output_name).write_text(draft.rstrip() + "\n", encoding="utf-8")
            self._set_step("write", "complete", attempts=1, detail=str(output_path))

            verifier, deterministic, source_checks = await self._verify(draft, phase="independent_verify")
            self.session.verifier = verifier
            self.session.deterministic_checks = deterministic
            self.session.source_checks = source_checks
            self._persist()

            if not verifier.get("pass"):
                self.session.steps.extend(StepRecord(name=x) for x in self.OPTIONAL_STEPS)
                corrected = self._strip_code_fence(
                    await self._provider_call(
                        "single_correction",
                        self._correction_prompt(draft, deterministic, verifier, research),
                        max_output_tokens=4200,
                    )
                )
                output_path.write_text(corrected.rstrip() + "\n", encoding="utf-8")
                (run_root / self.spec.output_name).write_text(corrected.rstrip() + "\n", encoding="utf-8")
                final_verifier, final_det, final_sources = await self._verify(corrected, phase="final_verify")
                self.session.verifier = final_verifier
                self.session.deterministic_checks = final_det
                self.session.source_checks = final_sources
                self._persist()
                verifier = final_verifier

            if not verifier.get("pass"):
                raise RuntimeError(
                    "verificación final FAIL: "
                    + "; ".join(str(x) for x in verifier.get("provider_reasons") or ["contrato no satisfecho"])
                )

            if not output_path.is_file() or output_path.stat().st_size <= 0:
                raise RuntimeError("el entregable verificado no existe o está vacío al cierre")

            self.session.status = "complete"
            self.session.stage = "closed"
            self.session.delivery_pass = True
            self.session.finished_at = time.time()
            self._persist()
            (run_root / "RESULT.json").write_text(
                json.dumps(self.session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return self.session.to_dict()
        except Exception as exc:
            assert self.session is not None
            self.session.status = "failed"
            self.session.stage = "failed"
            self.session.delivery_pass = False
            self.session.failure_reason = f"{type(exc).__name__}: {exc}"[:1600]
            self.session.finished_at = time.time()
            self._persist()
            (run_root / "RESULT.json").write_text(
                json.dumps(self.session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            return self.session.to_dict()
