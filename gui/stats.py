"""Lightweight SQLite stats for the dashboard."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "pokehunt.db"


def _connect() -> Optional[sqlite3.Connection]:
    if not DB_PATH.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error:
        return None


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def fetch_dashboard_stats() -> dict[str, Any]:
    stats: dict[str, Any] = {
        "db_exists": DB_PATH.exists(),
        "pings_10d": 0,
        "pings_total": 0,
        "media_10d": 0,
        "chat_7d": 0,
        "hunters_earned": 0,
        "whitelist": 0,
        "top_stores": [],  # list[(store, count)]
        "recent_pings": [],  # list[dict]
    }
    conn = _connect()
    if conn is None:
        return stats
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pings WHERE timestamp >= ?", (_days_ago_iso(10),))
        stats["pings_10d"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM pings")
        stats["pings_total"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM media WHERE timestamp >= ?", (_days_ago_iso(10),))
        stats["media_10d"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM chat WHERE timestamp >= ?", (_days_ago_iso(7),))
        stats["chat_7d"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM hunter_role_earned")
        stats["hunters_earned"] = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM whitelist")
        stats["whitelist"] = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COALESCE(store, 'unknown') AS store, COUNT(*) AS c
            FROM pings
            WHERE timestamp >= ?
            GROUP BY store
            ORDER BY c DESC
            LIMIT 6
            """,
            (_days_ago_iso(10),),
        )
        stats["top_stores"] = [(row["store"], row["c"]) for row in cur.fetchall()]
        cur.execute(
            """
            SELECT store, mention_type, location, timestamp
            FROM pings
            ORDER BY timestamp DESC
            LIMIT 8
            """
        )
        stats["recent_pings"] = [dict(row) for row in cur.fetchall()]
    except sqlite3.Error:
        pass
    finally:
        conn.close()
    return stats
