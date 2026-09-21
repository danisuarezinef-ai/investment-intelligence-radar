from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import ProjectState, Task


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class QuotaDecision:
    allowed: bool
    reason: str
    retry_after_seconds: int
    counters: dict[str, float]
    limits: dict[str, float | None]
    checked_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QuotaGovernorV2:
    """Hard local resource quotas independent from monetary budget accounting.

    Quotas are opt-in and default to no additional restriction. Usage is accumulated
    in minute buckets, so the audit trail may stay bounded without losing quota usage
    under high-throughput workloads. The governor cannot buy or raise capacity.
    """

    KEY = "quota_governor_v2"
    EVENTS = "quota_events_v2"
    BUCKETS = "quota_buckets_v2"
    DEFAULTS = {
        "provider_calls_per_hour": None,
        "dispatches_per_hour": None,
        "external_actions_per_day": None,
        "compute_seconds_per_hour": None,
    }

    @classmethod
    def limits(cls, state: ProjectState) -> dict[str, float | None]:
        raw = dict(cls.DEFAULTS)
        configured = dict(state.metadata.get("resource_quotas_v2", {}) or {})
        for key in raw:
            value = configured.get(key, raw[key])
            if value is None:
                raw[key] = None
            else:
                raw[key] = max(0.0, float(value))
        return raw

    @staticmethod
    def _parse_ts(value: str) -> datetime | None:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _bucket_key(now: datetime, kind: str) -> str:
        minute = now.astimezone(timezone.utc).replace(second=0, microsecond=0)
        return f"{minute.isoformat()}|{kind}"

    def _prune(self, state: ProjectState, now: datetime) -> None:
        # Audit rows are intentionally small/bounded; quota correctness lives in the
        # minute buckets below and therefore survives event-history compaction.
        events = list(state.metadata.get(self.EVENTS, []) or [])
        state.metadata[self.EVENTS] = events[-1000:]
        buckets = dict(state.metadata.get(self.BUCKETS, {}) or {})
        cutoff = now - timedelta(days=2, minutes=2)
        kept: dict[str, float] = {}
        for key, value in buckets.items():
            ts_text = str(key).rsplit("|", 1)[0]
            ts = self._parse_ts(ts_text)
            if ts is not None and ts >= cutoff:
                kept[str(key)] = max(0.0, float(value or 0.0))
        state.metadata[self.BUCKETS] = kept

    def _migrate_legacy_events(self, state: ProjectState, now: datetime) -> None:
        events = list(state.metadata.get(self.EVENTS, []) or [])
        buckets: dict[str, float] = {}
        cutoff = now - timedelta(days=2, minutes=2)
        kept: list[dict[str, Any]] = []
        for event in events:
            ts = self._parse_ts(str(event.get("ts") or ""))
            if ts is None or ts < cutoff:
                continue
            kept.append(event)
            kind = str(event.get("kind") or "")
            units = max(0.0, float(event.get("units", 1.0) or 0.0))
            key = self._bucket_key(ts, kind)
            buckets[key] = float(buckets.get(key, 0.0) or 0.0) + units
        state.metadata[self.BUCKETS] = buckets
        state.metadata[self.EVENTS] = kept[-1000:]

    def counters(self, state: ProjectState, *, now: datetime | None = None) -> dict[str, float]:
        now = now or _now()
        buckets = dict(state.metadata.get(self.BUCKETS, {}) or {})
        if not buckets and state.metadata.get(self.EVENTS):
            self._migrate_legacy_events(state, now)
        self._prune(state, now)
        buckets = dict(state.metadata.get(self.BUCKETS, {}) or {})
        hour = now - timedelta(hours=1)
        day = now - timedelta(days=1)
        result = {"provider_calls_hour": 0.0, "dispatches_hour": 0.0, "external_actions_day": 0.0, "compute_seconds_hour": 0.0}
        for key, units in buckets.items():
            try:
                ts_text, kind = str(key).rsplit("|", 1)
            except ValueError:
                continue
            ts = self._parse_ts(ts_text)
            if ts is None:
                continue
            value = max(0.0, float(units or 0.0))
            if ts >= hour:
                if kind == "provider_call": result["provider_calls_hour"] += value
                elif kind == "dispatch": result["dispatches_hour"] += value
                elif kind == "compute_seconds": result["compute_seconds_hour"] += value
            if ts >= day and kind == "external_action":
                result["external_actions_day"] += value
        return result

    def assess_dispatch(self, state: ProjectState, task: Task, *, now: datetime | None = None) -> QuotaDecision:
        now = now or _now()
        limits = self.limits(state)
        counters = self.counters(state, now=now)
        checks = [
            ("dispatches_per_hour", "dispatches_hour", 3600),
            ("provider_calls_per_hour", "provider_calls_hour", 3600),
        ]
        external = bool(task.metadata.get("external_action")) or any(
            str(c).lower() in {"external_write", "publication", "remote_publish", "payment", "spending", "trade_real", "real_trading"}
            for c in task.required_capabilities
        )
        if external:
            checks.append(("external_actions_per_day", "external_actions_day", 86400))
        for limit_key, counter_key, window in checks:
            limit = limits[limit_key]
            if limit is not None and counters[counter_key] >= limit:
                decision = QuotaDecision(False, f"quota_exhausted:{limit_key}", window, counters, limits, now.isoformat())
                state.metadata[self.KEY] = decision.to_dict()
                return decision
        decision = QuotaDecision(True, "within_quota", 0, counters, limits, now.isoformat())
        state.metadata[self.KEY] = decision.to_dict()
        return decision

    def record(self, state: ProjectState, kind: str, *, units: float = 1.0, task_id: str | None = None, now: datetime | None = None) -> None:
        now = now or _now()
        units = max(0.0, float(units))
        buckets = state.metadata.setdefault(self.BUCKETS, {})
        key = self._bucket_key(now, str(kind))
        buckets[key] = float(buckets.get(key, 0.0) or 0.0) + units
        events = state.metadata.setdefault(self.EVENTS, [])
        events.append({"ts": now.isoformat(), "kind": str(kind), "units": units, "task_id": task_id})
        if len(events) > 1000:
            del events[:-1000]
        # Bucket pruning is cheap and bounds two days of minute-resolution history.
        if len(buckets) > 12_000:
            self._prune(state, now)

    def record_dispatch(self, state: ProjectState, task: Task) -> None:
        self.record(state, "dispatch", task_id=task.id)
        external = bool(task.metadata.get("external_action")) or any(
            str(c).lower() in {"external_write", "publication", "remote_publish", "payment", "spending", "trade_real", "real_trading"}
            for c in task.required_capabilities
        )
        if external:
            self.record(state, "external_action", task_id=task.id)

    def record_provider_call(self, state: ProjectState, task: Task) -> None:
        self.record(state, "provider_call", task_id=task.id)

    def record_compute_seconds(self, state: ProjectState, task: Task, seconds: float) -> None:
        if seconds > 0:
            self.record(state, "compute_seconds", units=float(seconds), task_id=task.id)
