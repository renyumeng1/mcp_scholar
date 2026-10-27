"""Simple SQLite cache with TTL for academic lookups."""
import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Optional

CACHE_DB = Path.home() / ".mcp_scholar_cache.db"
DEFAULT_TTL = 3600 * 6  # 6 hours


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT,
            expires_at REAL
        )
        """
    )
    return conn


def cache_get(key: str) -> Optional[Any]:
    try:
        with _get_conn() as conn:
            row = conn.execute(
                "SELECT value, expires_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if not row:
                return None
            value, expires_at = row
            if expires_at < time.time():
                conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                return None
            return json.loads(value)
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    try:
        expires = time.time() + ttl
        with _get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(value, ensure_ascii=False), expires),
            )
    except Exception:
        pass
