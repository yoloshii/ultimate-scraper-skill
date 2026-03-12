"""Unit tests for RateLimiter."""

import time
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from rate_limiting.limiter import RateLimiter, get_rate_limiter


class TestRateLimiter:
    """Tests for the sliding-window rate limiter."""

    @pytest.fixture
    def limiter(self):
        return RateLimiter(limits={"default": 3, "slow.com": 1})

    def test_allows_within_limit(self, limiter):
        """Actions within limit are allowed."""
        assert limiter.check("example.com") is True
        limiter.record("example.com")
        assert limiter.check("example.com") is True

    def test_blocks_at_limit(self, limiter):
        """Actions at limit are blocked."""
        for _ in range(3):
            limiter.record("example.com")
        assert limiter.check("example.com") is False

    def test_domain_specific_limit(self, limiter):
        """Domain-specific limits are honored."""
        limiter.record("slow.com")
        assert limiter.check("slow.com") is False

    def test_wait_time_zero_when_allowed(self, limiter):
        """wait_time returns 0 when action is allowed."""
        assert limiter.wait_time("example.com") == 0.0

    def test_wait_time_positive_when_blocked(self, limiter):
        """wait_time returns positive when rate limited."""
        for _ in range(3):
            limiter.record("example.com")
        wait = limiter.wait_time("example.com")
        assert wait > 0.0
        assert wait <= 60.0

    def test_domains_isolated(self, limiter):
        """Different domains have independent windows."""
        for _ in range(3):
            limiter.record("a.com")
        assert limiter.check("a.com") is False
        assert limiter.check("b.com") is True

    def test_singleton_returns_same_instance(self):
        """get_rate_limiter() returns the same instance."""
        a = get_rate_limiter()
        b = get_rate_limiter()
        assert a is b

    def test_default_limits_used(self):
        """Default limits applied when no custom limits."""
        limiter = RateLimiter()
        assert limiter._get_limit("unknown.com") == 8
        assert limiter._get_limit("linkedin.com") == 4
