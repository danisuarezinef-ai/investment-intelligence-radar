import json, math, statistics
from datetime import datetime, timezone, timedelta

from radar_core import con, init_db, now, ASSETS, opportunity_rankings

def _dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00'))
    except Exception:
        return None

def init_intelligence_db():
    init_db()
    c = con()
    c.execute("""create table if not exists source_reputation(
        source text primary key,
        events integer not null default 0,
        actionable integer not null default 0,
        avg_abs_move real not null default 0,
        precision_proxy real not null default 0,
        confidence real not null default 0,
        score real not null default 0,
        updated_at text not null
    )""")
    c.execute("""create table if not exists silence_alerts(
        id integer primary key,
        ts text not null,
        symbol text not null,
        return_pct real not null,
        z_score real not null,
        recent_public_catalyst integer not null default 0,
        status text not null default 'OPEN',
        detail text
    )""")
    c.execute("""create table if not exists notifications(
        id integer primary key,
        ts text not null,
        kind text not null,
        severity text not null,
        title text not null,
        body text not null,
        symbol text,
        read integer not null default 0,
        dedupe_key text unique
    )""")
    c.execute("""create table if not exists sync_nodes(
        node_id text primary key,
        node_type text not null,
        name text,
        capabilities text,
        last_seen text not null,
        app_version text,
        detail text
    )""")
    c.execute("""create table if not exists intelligence_state(
        key text primary key,
        value text,
        updated_at text not null
    )""")
    c.execute("create index if not exists idx_silence_ts on silence_alerts(ts)")
    c.execute("create index if not exists idx_notifications_ts on notifications(ts)")
    c.commit()
    c.close()

def _daily_prices(symbol, days=50):
    c = con()
    since = (datetime.now(timezone.utc) - timedelta(days=days + 10)).isoformat()
    rows = c.execute(
        "select ts,price from market_snapshots where symbol=? and ts>=? order by ts",
        (symbol, since),
    ).fetchall()
    c.close()
    byday = {}
    for ts, p in rows:
        try:
            byday[str(ts)[:10]] = float(p)
        except Exception:
            pass
    return sorted(byday.items())

def _returns(rows):
    out = []
    for i in range(1, len(rows)):
        a, b = rows[i-1][1], rows[i][1]
        if a and b:
            out.append((rows[i][0], (b / a - 1.0) * 100.0))
    return out

def _symbols_in_title(title):
    t = " " + str(title or "").upper().replace("·", " ").replace("-", " ") + " "
    found = []
    for sym in ASSETS:
        token = sym.upper()
        if f" {token} " in t:
            found.append(sym)
    return found

def enqueue_notification(kind, severity, title, body, symbol=None, dedupe_key=None):
    init_intelligence_db()
    c = con()
    try:
        c.execute(
            """insert into notifications(ts,kind,severity,title,body,symbol,read,dedupe_key)
               values(?,?,?,?,?,?,0,?)""",
            (now(), kind, severity, title, body, symbol, dedupe_key),
        )
        c.commit()
        created = True
    except Exception:
        created = False
    c.close()
    return created

def list_notifications(limit=50, unread_only=False):
    init_intelligence_db()
    c = con()
    sql = "select id,ts,kind,severity,title,body,symbol,read from notifications"
    args = []
    if unread_only:
        sql += " where read=0"
    sql += " order by id desc limit ?"
    args.append(max(1, min(int(limit), 200)))
    rows = c.execute(sql, args).fetchall()
    c.close()
    return [
        dict(id=r[0], ts=r[1], kind=r[2], severity=r[3], title=r[4],
             body=r[5], symbol=r[6], read=bool(r[7]))
        for r in rows
    ]

def mark_notifications_read(ids=None):
    init_intelligence_db()
    c = con()
    if ids:
        clean = [int(x) for x in ids if str(x).isdigit()]
        if clean:
            q = ",".join("?" for _ in clean)
            c.execute(f"update notifications set read=1 where id in ({q})", clean)
    else:
        c.execute("update notifications set read=1")
    c.commit()
    n = c.total_changes
    c.close()
    return n

def detect_silence(z_threshold=2.25, catalyst_hours=12):
    init_intelligence_db()
    created = []
    now_dt = datetime.now(timezone.utc)
    catalyst_since = (now_dt - timedelta(hours=catalyst_hours)).isoformat()
    c = con()
    for symbol in ASSETS:
        rows = _daily_prices(symbol, 55)
        rets = _returns(rows)
        if len(rets) < 12:
            continue
        hist = [x[1] for x in rets[:-1]][-40:]
        latest = rets[-1][1]
        sd = statistics.pstdev(hist) if len(hist) > 2 else 0.0
        mu = statistics.mean(hist) if hist else 0.0
        if sd <= 1e-9:
            continue
        z = (latest - mu) / sd
        if abs(z) < z_threshold:
            continue
        recent = c.execute(
            """select count(*) from information_events
               where ts>=? and upper(title) like ?""",
            (catalyst_since, f"%{symbol.upper()}%"),
        ).fetchone()[0]
        if recent:
            continue
        day = rows[-1][0]
        exists = c.execute(
            "select 1 from silence_alerts where symbol=? and substr(ts,1,10)=? limit 1",
            (symbol, day),
        ).fetchone()
        if exists:
            continue
        severity = "HIGH" if abs(z) >= 3.0 else "MEDIUM"
        detail = (
            f"Movimiento diario {latest:+.2f}% (z={z:+.2f}) sin catalizador público "
            f"detectado en las últimas {catalyst_hours} h."
        )
        c.execute(
            """insert into silence_alerts(ts,symbol,return_pct,z_score,recent_public_catalyst,status,detail)
               values(?,?,?,?,0,'OPEN',?)""",
            (now(), symbol, latest, z, detail),
        )
        dedupe = f"silence:{symbol}:{day}"
        enqueue_notification(
            "silence", severity,
            f"Movimiento sin catalizador: {symbol}",
            detail, symbol=symbol, dedupe_key=dedupe
        )
        created.append(dict(symbol=symbol, return_pct=latest, z_score=z, severity=severity, detail=detail))
    c.commit()
    c.close()
    return created

def silence_alerts(limit=50, open_only=True):
    init_intelligence_db()
    c = con()
    sql = """select id,ts,symbol,return_pct,z_score,recent_public_catalyst,status,detail
             from silence_alerts"""
    if open_only:
        sql += " where status='OPEN'"
    sql += " order by id desc limit ?"
    rows = c.execute(sql, (max(1, min(int(limit), 200)),)).fetchall()
    c.close()
    return [
        dict(id=r[0], ts=r[1], symbol=r[2], return_pct=r[3], z_score=r[4],
             recent_public_catalyst=bool(r[5]), status=r[6], detail=r[7])
        for r in rows
    ]

def _price_near(symbol, when, direction):
    c = con()
    if direction == "before":
        row = c.execute(
            "select price,ts from market_snapshots where symbol=? and ts<=? order by ts desc limit 1",
            (symbol, when),
        ).fetchone()
    else:
        row = c.execute(
            "select price,ts from market_snapshots where symbol=? and ts>=? order by ts asc limit 1",
            (symbol, when),
        ).fetchone()
    c.close()
    return row

def evaluate_source_reputation(window_days=90):
    init_intelligence_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).isoformat()
    c = con()
    sources = [r[0] for r in c.execute(
        "select distinct source from information_events where ts>=?", (cutoff,)
    ).fetchall()]
    results = []
    for source in sources:
        events = c.execute(
            "select ts,title from information_events where source=? and ts>=? order by ts",
            (source, cutoff),
        ).fetchall()
        moves = []
        actionable = 0
        directional_hits = 0
        for ts, title in events:
            syms = _symbols_in_title(title)
            if not syms:
                continue
            event_dt = _dt(ts)
            if not event_dt:
                continue
            for sym in syms:
                before = _price_near(sym, event_dt.isoformat(), "before")
                after_t = (event_dt + timedelta(hours=36)).isoformat()
                after = _price_near(sym, after_t, "after")
                if not before or not after:
                    continue
                try:
                    move = (float(after[0]) / float(before[0]) - 1.0) * 100.0
                except Exception:
                    continue
                actionable += 1
                moves.append(abs(move))
                if abs(move) >= 1.0:
                    directional_hits += 1
        avg_move = statistics.mean(moves) if moves else 0.0
        precision = (directional_hits / actionable) if actionable else 0.0
        confidence = min(1.0, actionable / 20.0)
        coverage = min(1.0, len(events) / 50.0)
        score = 100.0 * (
            0.25 * coverage
            + 0.35 * min(avg_move / 4.0, 1.0)
            + 0.25 * precision
            + 0.15 * confidence
        )
        c.execute(
            """insert into source_reputation(source,events,actionable,avg_abs_move,precision_proxy,confidence,score,updated_at)
               values(?,?,?,?,?,?,?,?)
               on conflict(source) do update set
                 events=excluded.events, actionable=excluded.actionable,
                 avg_abs_move=excluded.avg_abs_move, precision_proxy=excluded.precision_proxy,
                 confidence=excluded.confidence, score=excluded.score, updated_at=excluded.updated_at""",
            (source, len(events), actionable, avg_move, precision, confidence, score, now()),
        )
        results.append(dict(
            source=source, events=len(events), actionable=actionable,
            avg_abs_move=avg_move, precision_proxy=precision,
            confidence=confidence, score=score
        ))
    c.commit()
    c.close()
    return sorted(results, key=lambda x: x["score"], reverse=True)

def source_reputation(limit=50):
    init_intelligence_db()
    c = con()
    rows = c.execute(
        """select source,events,actionable,avg_abs_move,precision_proxy,confidence,score,updated_at
           from source_reputation order by score desc limit ?""",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    c.close()
    return [
        dict(source=r[0], events=r[1], actionable=r[2], avg_abs_move=r[3],
             precision_proxy=r[4], confidence=r[5], score=r[6], updated_at=r[7])
        for r in rows
    ]

def sync_node_heartbeat(node_id, node_type="desktop", name=None, capabilities=None,
                        app_version=None, detail=None):
    init_intelligence_db()
    node_id = str(node_id or "").strip()
    if not node_id:
        raise ValueError("node_id requerido")
    caps = capabilities
    if not isinstance(caps, str):
        caps = json.dumps(caps or [], ensure_ascii=False)
    c = con()
    c.execute(
        """insert into sync_nodes(node_id,node_type,name,capabilities,last_seen,app_version,detail)
           values(?,?,?,?,?,?,?)
           on conflict(node_id) do update set
             node_type=excluded.node_type,name=excluded.name,capabilities=excluded.capabilities,
             last_seen=excluded.last_seen,app_version=excluded.app_version,detail=excluded.detail""",
        (node_id, node_type, name, caps, now(), app_version, detail),
    )
    c.commit()
    c.close()
    return dict(node_id=node_id, node_type=node_type, last_seen=now())

def sync_nodes(limit=100):
    init_intelligence_db()
    c = con()
    rows = c.execute(
        """select node_id,node_type,name,capabilities,last_seen,app_version,detail
           from sync_nodes order by last_seen desc limit ?""",
        (max(1, min(int(limit), 200)),),
    ).fetchall()
    c.close()
    out = []
    for r in rows:
        try:
            caps = json.loads(r[3] or "[]")
        except Exception:
            caps = r[3]
        out.append(dict(
            node_id=r[0], node_type=r[1], name=r[2], capabilities=caps,
            last_seen=r[4], app_version=r[5], detail=r[6]
        ))
    return out

def intelligence_summary():
    init_intelligence_db()
    return {
        "source_reputation": source_reputation(10),
        "silence_alerts": silence_alerts(20, True),
        "notifications": list_notifications(20, False),
        "nodes": sync_nodes(20),
    }

def run_intelligence_cycle():
    alerts = detect_silence()
    reps = evaluate_source_reputation()
    return {
        "silence_created": len(alerts),
        "sources_scored": len(reps),
        "unread_notifications": len(list_notifications(200, True)),
    }
