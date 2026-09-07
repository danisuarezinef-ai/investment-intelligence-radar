from datetime import datetime, timezone, timedelta

import radar_core
import radar_intelligence as ri

def _use_tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "radar.db")
    monkeypatch.setattr(radar_core, "DB", db)
    monkeypatch.setattr(radar_core, "STATUS", str(tmp_path / "status.json"))
    monkeypatch.setattr(radar_core, "LOG", str(tmp_path / "worker.log"))
    monkeypatch.setattr(radar_core, "PID", str(tmp_path / "worker.pid"))
    radar_core.init_db()
    ri.init_intelligence_db()
    return db

def test_intelligence_schema_and_notification_dedupe(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    assert ri.enqueue_notification("test", "LOW", "A", "B", dedupe_key="same")
    assert not ri.enqueue_notification("test", "LOW", "A", "B", dedupe_key="same")
    rows = ri.list_notifications()
    assert len(rows) == 1
    assert rows[0]["title"] == "A"

def test_sync_node_heartbeat(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    ri.sync_node_heartbeat("pc-1", name="Desktop", capabilities=["collector"], app_version="1.3.0")
    nodes = ri.sync_nodes()
    assert nodes[0]["node_id"] == "pc-1"
    assert "collector" in nodes[0]["capabilities"]

def test_silence_detector_creates_alert(tmp_path, monkeypatch):
    _use_tmp_db(tmp_path, monkeypatch)
    c = radar_core.con()
    start = datetime.now(timezone.utc) - timedelta(days=25)
    price = 100.0
    for i in range(24):
        price *= 1.006 if i % 2 == 0 else 0.996
        ts = (start + timedelta(days=i)).replace(hour=21).isoformat()
        c.execute(
            "insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)",
            (ts, "MSFT", price, 1_000_000, "test"),
        )
    price *= 1.12
    ts = (start + timedelta(days=24)).replace(hour=21).isoformat()
    c.execute(
        "insert into market_snapshots(ts,symbol,price,volume,source) values(?,?,?,?,?)",
        (ts, "MSFT", price, 1_000_000, "test"),
    )
    c.commit()
    c.close()

    alerts = ri.detect_silence(z_threshold=2.0)
    assert any(a["symbol"] == "MSFT" for a in alerts)
    assert any(n["kind"] == "silence" for n in ri.list_notifications())
