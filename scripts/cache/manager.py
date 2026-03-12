"""SQLite-based result caching with TTL."""

import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from core.config import get_config


class CacheManager:
    """SQLite-based result caching with TTL."""

    def __init__(self, db_path: Optional[Path] = None, ttl_hours: int = 24):
        config = get_config()
        self.db_path = db_path or config.cache_dir / "cache.db"
        self.ttl_hours = ttl_hours
        self._init_db()

    def _init_db(self) -> None:
        """Initialize cache database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scrape_cache (
                cache_key TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                mode TEXT,
                tier_used INTEGER,
                status_code INTEGER,
                html TEXT,
                markdown TEXT,
                extracted_data TEXT,
                static_data TEXT,
                metadata TEXT,
                fetched_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires ON scrape_cache(expires_at)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_url ON scrape_cache(url)
        """)
        conn.commit()
        conn.close()

    def _make_key(self, url: str, mode: str = "auto", extract_prompt: Optional[str] = None) -> str:
        """Generate cache key from request parameters."""
        key_data = f"{url}|{mode}|{extract_prompt or ''}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]

    def get(self, url: str, mode: str = "auto", extract_prompt: Optional[str] = None) -> Optional[dict]:
        """Retrieve cached result if valid."""
        cache_key = self._make_key(url, mode, extract_prompt)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT url, mode, tier_used, status_code, html, markdown,
                   extracted_data, static_data, metadata, fetched_at
            FROM scrape_cache
            WHERE cache_key = ? AND expires_at > ?
            """,
            (cache_key, datetime.now().isoformat())
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "url": row[0],
                "mode": row[1],
                "tier_used": row[2],
                "status_code": row[3],
                "html": row[4],
                "markdown": row[5],
                "extracted_data": json.loads(row[6]) if row[6] else None,
                "static_data": json.loads(row[7]) if row[7] else None,
                "metadata": json.loads(row[8]) if row[8] else {},
                "fetched_at": row[9],
                "from_cache": True,
            }
        return None

    def set(
        self,
        url: str,
        mode: str,
        result: "ScrapeResult",
        extract_prompt: Optional[str] = None,
        ttl_hours: Optional[int] = None,
    ) -> None:
        """Store result in cache."""
        cache_key = self._make_key(url, mode, extract_prompt)
        now = datetime.now()
        expires = now + timedelta(hours=ttl_hours or self.ttl_hours)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO scrape_cache
            (cache_key, url, mode, tier_used, status_code, html, markdown,
             extracted_data, static_data, metadata, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                url,
                mode,
                result.tier_used,
                result.status_code,
                result.html,
                result.markdown,
                json.dumps(result.extracted_data) if result.extracted_data else None,
                json.dumps(result.static_data) if result.static_data else None,
                json.dumps(result.metadata),
                now.isoformat(),
                expires.isoformat(),
            )
        )
        conn.commit()
        conn.close()

    def invalidate(self, url: str, mode: str = "auto") -> bool:
        """Invalidate a specific cache entry."""
        cache_key = self._make_key(url, mode)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM scrape_cache WHERE cache_key = ?",
            (cache_key,)
        )
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def cleanup_expired(self) -> int:
        """Remove expired cache entries. Returns count of deleted entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM scrape_cache WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    def clear_all(self) -> int:
        """Clear all cache entries. Returns count of deleted entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM scrape_cache")
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    def stats(self) -> dict:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM scrape_cache")
        total = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT COUNT(*) FROM scrape_cache WHERE expires_at > ?",
            (datetime.now().isoformat(),)
        )
        valid = cursor.fetchone()[0]

        cursor = conn.execute(
            "SELECT SUM(LENGTH(html) + LENGTH(markdown)) FROM scrape_cache"
        )
        size_bytes = cursor.fetchone()[0] or 0
        conn.close()

        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": total - valid,
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
        }
