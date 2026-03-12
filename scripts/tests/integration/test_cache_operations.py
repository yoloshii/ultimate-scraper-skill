"""Integration tests for cache operations."""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
import time

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.integration
class TestCacheOperations:
    """Integration tests for cache database operations."""

    def test_cache_set_and_get(self, cache_manager):
        """Set cache entry, get returns same data."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            tier_used=2,
            status_code=200,
            html="<html>cached content</html>",
            markdown="# Cached Content",
            url="https://cached-test.com",
        )

        # Set cache
        cache_manager.set(
            url="https://cached-test.com",
            mode="auto",
            result=result
        )

        # Get cache
        cached = cache_manager.get(
            url="https://cached-test.com",
            mode="auto"
        )

        assert cached is not None
        assert cached["html"] == "<html>cached content</html>"
        assert cached["markdown"] == "# Cached Content"
        assert cached["tier_used"] == 2
        assert cached["from_cache"] is True

    def test_cache_ttl_expiration(self, cache_manager, temp_cache_db, monkeypatch):
        """Expired entries not returned by get()."""
        from cache.manager import CacheManager
        from core.result import ScrapeResult

        # Create manager with very short TTL (1 second)
        # Note: We can't actually expire in 1 second reliably, so we test the logic
        short_cache = CacheManager(db_path=temp_cache_db, ttl_hours=0)

        result = ScrapeResult(
            success=True,
            url="https://expire-test.com",
            html="<html>will expire</html>"
        )

        short_cache.set(
            url="https://expire-test.com",
            mode="auto",
            result=result,
            ttl_hours=0  # Expires immediately
        )

        # Wait a moment
        time.sleep(0.1)

        # Get should return None (expired)
        cached = short_cache.get(
            url="https://expire-test.com",
            mode="auto"
        )

        assert cached is None

    def test_cache_key_includes_prompt(self, cache_manager):
        """Different prompts = different cache keys."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            url="https://prompt-test.com",
            html="<html>content</html>",
            extracted_data={"version": 1}
        )

        # Cache with prompt 1
        cache_manager.set(
            url="https://prompt-test.com",
            mode="auto",
            result=result,
            extract_prompt="Extract product data"
        )

        # Different prompt should be different cache entry
        result2 = ScrapeResult(
            success=True,
            url="https://prompt-test.com",
            html="<html>content</html>",
            extracted_data={"version": 2}
        )

        cache_manager.set(
            url="https://prompt-test.com",
            mode="auto",
            result=result2,
            extract_prompt="Extract pricing"
        )

        # Get with first prompt
        cached1 = cache_manager.get(
            url="https://prompt-test.com",
            mode="auto",
            extract_prompt="Extract product data"
        )

        # Get with second prompt
        cached2 = cache_manager.get(
            url="https://prompt-test.com",
            mode="auto",
            extract_prompt="Extract pricing"
        )

        assert cached1["extracted_data"]["version"] == 1
        assert cached2["extracted_data"]["version"] == 2

    def test_cache_invalidate(self, cache_manager):
        """invalidate() removes specific entry."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            url="https://invalidate-test.com",
            html="<html>to be removed</html>"
        )

        cache_manager.set(
            url="https://invalidate-test.com",
            mode="auto",
            result=result
        )

        # Verify it's cached
        cached = cache_manager.get("https://invalidate-test.com", "auto")
        assert cached is not None

        # Invalidate
        invalidated = cache_manager.invalidate("https://invalidate-test.com", "auto")
        assert invalidated is True

        # Should be gone
        cached = cache_manager.get("https://invalidate-test.com", "auto")
        assert cached is None

    def test_cache_invalidate_nonexistent(self, cache_manager):
        """invalidate() returns False for missing entry."""
        result = cache_manager.invalidate("https://nonexistent.com", "auto")
        assert result is False

    def test_cache_cleanup_expired(self, cache_manager, temp_cache_db, monkeypatch):
        """cleanup_expired() removes old entries."""
        from cache.manager import CacheManager
        from core.result import ScrapeResult

        # Create with very short TTL
        short_cache = CacheManager(db_path=temp_cache_db, ttl_hours=0)

        result = ScrapeResult(
            success=True,
            url="https://cleanup-test.com",
            html="<html>old content</html>"
        )

        short_cache.set(
            url="https://cleanup-test.com",
            mode="auto",
            result=result,
            ttl_hours=0  # Expires immediately
        )

        # Wait a moment
        time.sleep(0.1)

        # Cleanup
        deleted = short_cache.cleanup_expired()

        assert deleted >= 1

    def test_cache_clear_all(self, cache_manager):
        """clear_all() removes all entries."""
        from core.result import ScrapeResult

        # Add several entries
        for i in range(5):
            result = ScrapeResult(
                success=True,
                url=f"https://clear-test-{i}.com",
                html=f"<html>content {i}</html>"
            )
            cache_manager.set(f"https://clear-test-{i}.com", "auto", result)

        # Clear all
        deleted = cache_manager.clear_all()

        assert deleted >= 5

        # Verify empty
        stats = cache_manager.stats()
        assert stats["total_entries"] == 0

    def test_cache_stats(self, cache_manager):
        """stats() returns cache statistics."""
        from core.result import ScrapeResult

        # Add some entries
        for i in range(3):
            result = ScrapeResult(
                success=True,
                url=f"https://stats-test-{i}.com",
                html=f"<html>{'x' * 1000}</html>",
                markdown=f"{'x' * 500}"
            )
            cache_manager.set(f"https://stats-test-{i}.com", "auto", result)

        stats = cache_manager.stats()

        assert "total_entries" in stats
        assert "valid_entries" in stats
        assert "expired_entries" in stats
        assert "size_bytes" in stats
        assert "size_mb" in stats
        assert stats["total_entries"] >= 3
        assert stats["size_bytes"] > 0

    def test_cache_mode_separation(self, cache_manager):
        """Different modes create separate cache entries."""
        from core.result import ScrapeResult

        # Cache with mode "auto"
        result_auto = ScrapeResult(
            success=True,
            url="https://mode-test.com",
            html="<html>auto mode</html>"
        )
        cache_manager.set("https://mode-test.com", "auto", result_auto)

        # Cache with mode "stealth"
        result_stealth = ScrapeResult(
            success=True,
            url="https://mode-test.com",
            html="<html>stealth mode</html>"
        )
        cache_manager.set("https://mode-test.com", "stealth", result_stealth)

        # Get both
        cached_auto = cache_manager.get("https://mode-test.com", "auto")
        cached_stealth = cache_manager.get("https://mode-test.com", "stealth")

        assert cached_auto["html"] == "<html>auto mode</html>"
        assert cached_stealth["html"] == "<html>stealth mode</html>"

    def test_cache_with_extracted_data(self, cache_manager):
        """Cache stores and retrieves extracted data."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            url="https://extract-cache.com",
            html="<html>content</html>",
            extracted_data={"products": [{"name": "Widget", "price": 19.99}]}
        )

        cache_manager.set("https://extract-cache.com", "ai", result)

        cached = cache_manager.get("https://extract-cache.com", "ai")

        assert cached["extracted_data"] is not None
        assert cached["extracted_data"]["products"][0]["name"] == "Widget"

    def test_cache_with_static_data(self, cache_manager):
        """Cache stores and retrieves static data."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            url="https://static-cache.com",
            html="<html>content</html>",
            static_data={"next_data": {"props": {"page": "home"}}}
        )

        cache_manager.set("https://static-cache.com", "static", result)

        cached = cache_manager.get("https://static-cache.com", "static")

        assert cached["static_data"] is not None
        assert cached["static_data"]["next_data"]["props"]["page"] == "home"

    def test_cache_replaces_existing(self, cache_manager):
        """Setting same key replaces existing entry."""
        from core.result import ScrapeResult

        # First version
        result1 = ScrapeResult(
            success=True,
            url="https://replace-test.com",
            html="<html>version 1</html>"
        )
        cache_manager.set("https://replace-test.com", "auto", result1)

        # Second version (same key)
        result2 = ScrapeResult(
            success=True,
            url="https://replace-test.com",
            html="<html>version 2</html>"
        )
        cache_manager.set("https://replace-test.com", "auto", result2)

        # Should get version 2
        cached = cache_manager.get("https://replace-test.com", "auto")
        assert cached["html"] == "<html>version 2</html>"
