"""Unit tests for FingerprintProfile and FingerprintManager."""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


class TestFingerprintProfile:
    """Tests for FingerprintProfile dataclass."""

    def test_fingerprint_profile_to_dict(self, fingerprint_manager):
        """FingerprintProfile.to_dict() returns all fields."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test123",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US,en;q=0.9",
            platform="Win32",
            geo="us",
        )
        result = fp.to_dict()

        assert result["fingerprint_id"] == "test123"
        assert result["domain"] == "example.com"
        assert result["browser"] == "chrome"
        assert result["browser_version"] == "chrome143"
        assert result["platform"] == "Win32"
        assert "created_at" in result
        assert "last_used_at" in result

    def test_fingerprint_profile_from_dict(self, fingerprint_manager):
        """FingerprintProfile.from_dict() reconstructs object."""
        from fingerprint.manager import FingerprintProfile

        data = {
            "fingerprint_id": "test456",
            "domain": "test.com",
            "browser": "firefox",
            "browser_version": "firefox135",
            "impersonate": "firefox135",
            "user_agent": "Mozilla/5.0...",
            "accept_language": "de-DE,de;q=0.9",
            "platform": "Linux x86_64",
            "geo": "de",
            "created_at": "2024-01-01T00:00:00",
            "last_used_at": "2024-01-01T00:00:00",
            "use_count": 5,
            "blocked_count": 1,
            "success_count": 4,
        }
        fp = FingerprintProfile.from_dict(data)

        assert fp.fingerprint_id == "test456"
        assert fp.domain == "test.com"
        assert fp.browser == "firefox"
        assert fp.geo == "de"
        assert fp.use_count == 5

    def test_fingerprint_profile_touch_updates_timestamp(self, fingerprint_manager):
        """touch() updates last_used_at and increments use_count."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test789",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
        )
        original_timestamp = fp.last_used_at
        original_use_count = fp.use_count

        # Small delay to ensure timestamp difference
        import time
        time.sleep(0.01)

        fp.touch()

        assert fp.last_used_at != original_timestamp
        assert fp.use_count == original_use_count + 1

    def test_fingerprint_profile_record_success(self, fingerprint_manager):
        """record_success() increments success_count."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
        )
        initial = fp.success_count

        fp.record_success()

        assert fp.success_count == initial + 1
        assert fp.use_count == 1

    def test_fingerprint_profile_record_block(self, fingerprint_manager):
        """record_block() increments blocked_count."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
        )
        initial = fp.blocked_count

        fp.record_block()

        assert fp.blocked_count == initial + 1
        assert fp.use_count == 1

    def test_fingerprint_profile_block_rate_calculation(self, fingerprint_manager):
        """block_rate property calculates correctly (blocked / total)."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            blocked_count=3,
            success_count=7,
        )

        assert fp.block_rate == pytest.approx(0.3)  # 3 / 10

    def test_fingerprint_profile_block_rate_zero_division(self, fingerprint_manager):
        """block_rate returns 0.0 when no requests made."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            blocked_count=0,
            success_count=0,
        )

        assert fp.block_rate == 0.0


class TestFingerprintManager:
    """Tests for FingerprintManager."""

    def test_normalize_domain_from_url(self, fingerprint_manager):
        """_normalize_domain('https://www.example.com/path') -> 'example.com'."""
        result = fingerprint_manager._normalize_domain("https://www.example.com/path?query=1")
        assert result == "example.com"

    def test_normalize_domain_strips_www(self, fingerprint_manager):
        """_normalize_domain('www.test.com') -> 'test.com'."""
        result = fingerprint_manager._normalize_domain("www.test.com")
        assert result == "test.com"

    def test_normalize_domain_lowercases(self, fingerprint_manager):
        """_normalize_domain('Example.COM') -> 'example.com'."""
        result = fingerprint_manager._normalize_domain("Example.COM")
        assert result == "example.com"

    def test_generate_id_length(self, fingerprint_manager):
        """_generate_id() returns 12 character string."""
        result = fingerprint_manager._generate_id()
        assert len(result) == 12
        assert result.isalnum()

    def test_generate_id_unique(self, fingerprint_manager):
        """Multiple _generate_id() calls return unique values."""
        ids = [fingerprint_manager._generate_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_select_browser_weighted_us(self, fingerprint_manager):
        """US geo favors Chrome (65% expected)."""
        # Run many selections and check Chrome dominates
        selections = [fingerprint_manager._select_browser_weighted('us') for _ in range(1000)]
        chrome_count = selections.count('chrome')

        # Chrome should be selected ~65% of the time (allow wide margin for randomness)
        assert chrome_count > 500  # At least 50% (being conservative)
        assert chrome_count < 800  # Not more than 80%

    def test_select_browser_weighted_de(self, fingerprint_manager):
        """German geo has higher Firefox share (25%)."""
        selections = [fingerprint_manager._select_browser_weighted('de') for _ in range(1000)]
        firefox_count = selections.count('firefox')

        # Firefox should be more common in Germany than US
        # Expected ~25%, allow range of 15-35%
        assert firefox_count > 150
        assert firefox_count < 350

    def test_select_browser_weighted_unknown_geo(self, fingerprint_manager):
        """Unknown geo falls back to US distribution."""
        selections = [fingerprint_manager._select_browser_weighted('xyz') for _ in range(100)]
        # Should still work (falls back to US)
        assert all(b in ['chrome', 'safari', 'edge', 'firefox'] for b in selections)

    def test_generate_user_agent_chrome_windows(self, fingerprint_manager):
        """Chrome + Win32 generates valid Windows UA string."""
        ua = fingerprint_manager._generate_user_agent('chrome', 'chrome143', 'Win32')

        assert 'Chrome/143' in ua
        assert 'Windows NT' in ua
        assert 'Mozilla/5.0' in ua

    def test_generate_user_agent_firefox_macos(self, fingerprint_manager):
        """Firefox + MacIntel generates valid macOS UA string."""
        ua = fingerprint_manager._generate_user_agent('firefox', 'firefox135', 'MacIntel')

        assert 'Firefox/135' in ua
        assert 'Macintosh' in ua
        assert 'Gecko' in ua

    def test_generate_user_agent_safari(self, fingerprint_manager):
        """Safari always generates macOS UA string."""
        ua = fingerprint_manager._generate_user_agent('safari', 'safari18', 'MacIntel')

        assert 'Safari' in ua
        assert 'Macintosh' in ua
        assert 'Version/18' in ua

    def test_generate_user_agent_edge(self, fingerprint_manager):
        """Edge generates Windows UA with Edg/ suffix."""
        ua = fingerprint_manager._generate_user_agent('edge', 'edge140', 'Win32')

        assert 'Edg/140' in ua
        assert 'Windows NT' in ua

    def test_should_rotate_missing_fingerprint(self, fingerprint_manager):
        """should_rotate() returns True for non-existent ID."""
        result = fingerprint_manager.should_rotate("nonexistent_id_12345")
        assert result is True

    def test_should_rotate_old_fingerprint(self, fingerprint_manager):
        """Fingerprint > 30 days old should rotate."""
        from fingerprint.manager import FingerprintProfile

        # Create old fingerprint
        old_date = (datetime.now() - timedelta(days=35)).isoformat()
        fp = FingerprintProfile(
            fingerprint_id="old_fp_123",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            created_at=old_date,
            last_used_at=old_date,
        )
        fingerprint_manager.save(fp)

        result = fingerprint_manager.should_rotate("old_fp_123")
        assert result is True

    def test_should_rotate_high_block_rate(self, fingerprint_manager):
        """Block rate > 30% should trigger rotation."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="blocked_fp",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            blocked_count=5,
            success_count=5,  # 50% block rate
        )
        fingerprint_manager.save(fp)

        result = fingerprint_manager.should_rotate("blocked_fp")
        assert result is True

    def test_should_rotate_consecutive_blocks(self, fingerprint_manager):
        """5+ blocks with 0 successes should rotate."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="only_blocked",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            blocked_count=6,
            success_count=0,
        )
        fingerprint_manager.save(fp)

        result = fingerprint_manager.should_rotate("only_blocked")
        assert result is True

    def test_should_not_rotate_healthy_fingerprint(self, fingerprint_manager):
        """Low block rate, recent fingerprint should not rotate."""
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="healthy_fp",
            domain="example.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            blocked_count=1,
            success_count=20,  # 5% block rate
        )
        fingerprint_manager.save(fp)

        result = fingerprint_manager.should_rotate("healthy_fp")
        assert result is False

    def test_get_or_create_creates_new(self, fingerprint_manager):
        """get_or_create creates new fingerprint for unknown domain."""
        fp = fingerprint_manager.get_or_create("newdomain.com", "us")

        assert fp is not None
        assert fp.domain == "newdomain.com"
        assert fp.geo == "us"
        assert fp.browser in ['chrome', 'safari', 'edge', 'firefox']

    def test_get_or_create_returns_existing(self, fingerprint_manager):
        """get_or_create returns existing fingerprint for same domain."""
        fp1 = fingerprint_manager.get_or_create("existing.com", "us")
        fp2 = fingerprint_manager.get_or_create("existing.com", "us")

        assert fp1.fingerprint_id == fp2.fingerprint_id
        assert fp1.user_agent == fp2.user_agent

    def test_list_fingerprints_by_domain(self, fingerprint_manager):
        """list_fingerprints(domain) filters correctly."""
        fingerprint_manager.get_or_create("site1.com", "us")
        fingerprint_manager.get_or_create("site2.com", "us")
        fingerprint_manager.get_or_create("site1.com", "de")  # Same domain, different geo

        site1_fps = fingerprint_manager.list_fingerprints("site1.com")

        assert len(site1_fps) >= 1
        assert all(fp["domain"] == "site1.com" for fp in site1_fps)

    def test_delete_fingerprint(self, fingerprint_manager):
        """delete() removes fingerprint from database."""
        fp = fingerprint_manager.get_or_create("todelete.com", "us")
        fp_id = fp.fingerprint_id

        result = fingerprint_manager.delete(fp_id)
        assert result is True

        # Verify deleted
        retrieved = fingerprint_manager.get_for_domain("todelete.com")
        assert retrieved is None

    def test_record_usage_success(self, fingerprint_manager):
        """record_usage updates success count."""
        fp = fingerprint_manager.get_or_create("usage.com", "us")
        initial_success = fp.success_count

        fingerprint_manager.record_usage(fp.fingerprint_id, success=True)

        updated = fingerprint_manager.get_for_domain("usage.com")
        assert updated.success_count == initial_success + 1

    def test_record_usage_block(self, fingerprint_manager):
        """record_usage updates blocked count."""
        fp = fingerprint_manager.get_or_create("blocked.com", "us")
        initial_blocked = fp.blocked_count

        fingerprint_manager.record_usage(fp.fingerprint_id, success=False)

        updated = fingerprint_manager.get_for_domain("blocked.com")
        assert updated.blocked_count == initial_blocked + 1
