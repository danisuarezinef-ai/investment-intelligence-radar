import json

import radar_paper_runtime_lease_v1 as lease


class _Resp:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self): return json.dumps(self.body).encode()


def test_acquire_marks_held_only_for_exact_owner_and_session(monkeypatch):
    monkeypatch.setattr(lease, "SYNC_TOKEN", "token")
    monkeypatch.setattr(lease, "SYNC_URL", "https://example.supabase.co/functions/v1/radar-sync")
    monkeypatch.setattr(lease.urllib.request, "urlopen", lambda req, timeout=10: _Resp({
        "ok": True, "lease": {"owner_id": "o", "session_id": "s", "real_trading": False}}))
    out = lease.acquire("o", "s")
    assert out["status"] == "HELD"
    assert out["real_trading"] is False


def test_transport_failure_fails_closed(monkeypatch):
    monkeypatch.setattr(lease, "SYNC_TOKEN", "token")
    monkeypatch.setattr(lease, "SYNC_URL", "https://example.supabase.co/functions/v1/radar-sync")
    def boom(*a, **k): raise TimeoutError("timeout")
    monkeypatch.setattr(lease.urllib.request, "urlopen", boom)
    out = lease.acquire("o", "s")
    assert out["status"] == "BLOCKED"
    assert out["held"] is False
    assert out["real_trading"] is False


def test_status_refuses_remote_real_trading_true(monkeypatch):
    monkeypatch.setattr(lease, "SYNC_TOKEN", "token")
    monkeypatch.setattr(lease, "SYNC_URL", "https://example.supabase.co/functions/v1/radar-sync")
    monkeypatch.setattr(lease.urllib.request, "urlopen", lambda req, timeout=10: _Resp({
        "ok": True, "lease": {"owner_id": "o", "session_id": "s", "real_trading": True}}))
    out = lease.status()
    assert out["status"] == "FAIL_CLOSED"
    assert out["real_trading"] is False
