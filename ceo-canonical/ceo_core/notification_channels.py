from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .models import ProjectState


@dataclass(slots=True)
class NotificationMessage:
    title: str
    body: str
    severity: str = "info"
    data: dict[str, Any] | None = None


class NotificationChannel(ABC):
    name = "channel"
    @abstractmethod
    async def send(self, message: NotificationMessage) -> bool: ...


class InMemoryNotificationChannel(NotificationChannel):
    name = "memory"
    def __init__(self) -> None: self.messages: list[NotificationMessage] = []
    async def send(self, message: NotificationMessage) -> bool:
        self.messages.append(message); return True


class MultiDeviceNotificationManager:
    """Fan-out abstraction for desktop/mobile/browser channels.

    Real push transports can be attached later without changing project logic.
    """
    def __init__(self, channels: list[NotificationChannel] | None = None) -> None:
        self.channels = channels or []

    async def publish(self, state: ProjectState, message: NotificationMessage) -> dict[str, bool]:
        if not state.notifications_enabled:
            return {}
        results: dict[str, bool] = {}
        for channel in self.channels:
            try: results[channel.name] = bool(await channel.send(message))
            except Exception: results[channel.name] = False
        state.metadata.setdefault("notification_delivery", []).append({"title": message.title, "results": results})
        return results

class WebhookNotificationChannel(NotificationChannel):
    """Generic mobile/desktop bridge. Endpoint/token are runtime config, never ProjectState."""
    name = "webhook"
    def __init__(self, endpoint: str, bearer_token: str | None = None, client=None) -> None:
        self.endpoint = endpoint; self.bearer_token = bearer_token; self._client = client
    async def send(self, message: NotificationMessage) -> bool:
        import httpx
        headers = {"Authorization": f"Bearer {self.bearer_token}"} if self.bearer_token else {}
        payload = {"title": message.title, "body": message.body, "severity": message.severity, "data": message.data or {}}
        if self._client is not None:
            response = await self._client.post(self.endpoint, json=payload, headers=headers)
            return 200 <= response.status_code < 300
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(self.endpoint, json=payload, headers=headers)
            return 200 <= response.status_code < 300

class DecisionResponseBridge:
    """Signs short-lived decision callbacks for paired device notification services."""
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 16: raise ValueError("Decision bridge secret must be at least 16 bytes")
        self.secret = secret
    def issue(self, decision_id: str, expires_unix: int) -> str:
        import base64, hashlib, hmac, json
        payload=json.dumps({"decision_id":decision_id,"exp":int(expires_unix)},separators=(',',':')).encode()
        sig=hmac.new(self.secret,payload,hashlib.sha256).digest()
        return base64.urlsafe_b64encode(payload+sig).decode().rstrip('=')
    def verify(self, token: str, now_unix: int) -> str | None:
        import base64, hashlib, hmac, json
        try:
            raw=base64.urlsafe_b64decode(token+'='*((4-len(token)%4)%4));payload,sig=raw[:-32],raw[-32:]
            if not hmac.compare_digest(sig,hmac.new(self.secret,payload,hashlib.sha256).digest()):return None
            row=json.loads(payload.decode())
            if int(row['exp']) < int(now_unix):return None
            return str(row['decision_id'])
        except Exception:return None
