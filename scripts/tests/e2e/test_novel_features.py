"""End-to-end tests for novel v1.2.0 features."""

import pytest
import sys
import statistics
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.e2e
class TestFingerprintConsistency:
    """E2E tests for fingerprint persistence."""

    def test_fingerprint_consistency_across_requests(self, fingerprint_manager):
        """Same domain gets same fingerprint across multiple scrapes."""
        domain = "consistency-test.example.com"

        # First request
        fp1 = fingerprint_manager.get_or_create(domain, "us")
        ua1 = fp1.user_agent
        browser1 = fp1.browser

        # Second request (simulating later)
        fp2 = fingerprint_manager.get_or_create(domain, "us")
        ua2 = fp2.user_agent
        browser2 = fp2.browser

        # Should be identical
        assert fp1.fingerprint_id == fp2.fingerprint_id
        assert ua1 == ua2
        assert browser1 == browser2

    def test_fingerprint_different_domains_different_identity(self, fingerprint_manager):
        """Different domains get different fingerprints."""
        fp1 = fingerprint_manager.get_or_create("site-a.com", "us")
        fp2 = fingerprint_manager.get_or_create("site-b.com", "us")

        # IDs should be different
        assert fp1.fingerprint_id != fp2.fingerprint_id

        # User agents might be same or different (random selection)
        # But at minimum IDs are unique

    def test_fingerprint_uniqueness_many_domains(self, fingerprint_manager):
        """100 different domains generate 100 unique fingerprints."""
        domains = [f"unique-site-{i}.com" for i in range(100)]
        fps = [fingerprint_manager.get_or_create(d, 'us') for d in domains]
        ids = [fp.fingerprint_id for fp in fps]

        assert len(set(ids)) == 100


@pytest.mark.e2e
class TestBehavioralSimulation:
    """E2E tests for behavioral simulation."""

    def test_bezier_curve_generates_path(self):
        """Bezier curve generates usable mouse path."""
        from behavior.human import BezierCurve

        start = (100, 100)
        end = (500, 400)

        points = BezierCurve.generate_points(start, end, steps=50)

        # Should have correct number of points
        assert len(points) == 51

        # Endpoints should match
        assert points[0] == start
        assert points[-1] == end

        # Path should progress generally toward end
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]

        # Should trend from start to end
        assert x_coords[-1] > x_coords[0]  # Moving right
        assert y_coords[-1] > y_coords[0]  # Moving down

    def test_typing_simulation_realistic(self):
        """Typing simulation produces realistic delays."""
        from behavior.human import HumanTyping

        text = "Hello, world!"
        delays = []

        prev_char = ""
        for char in text:
            delay = HumanTyping.get_inter_key_delay(char, prev_char)
            delays.append(delay)
            prev_char = char

        # Average delay should be around base delay
        avg = statistics.mean(delays)
        assert 30 < avg < 300  # Reasonable range

        # Should have variance
        std = statistics.stdev(delays)
        assert std > 5  # Not constant

    def test_reading_time_scales_with_content(self):
        """Reading time is proportional to content length."""
        from behavior.human import ReadingBehavior

        times = []
        for length in [100, 500, 1000, 2000, 5000]:
            # Average multiple samples
            samples = [ReadingBehavior.calculate_read_time(length) for _ in range(10)]
            times.append(statistics.mean(samples))

        # Each should be larger than previous (generally)
        # Due to randomness, allow some tolerance
        assert times[-1] > times[0]  # Longest > shortest


@pytest.mark.e2e
class TestJA4TDetection:
    """E2E tests for JA4T detection."""

    @pytest.mark.asyncio
    async def test_ja4t_sites_detected(self):
        """Known JA4T sites are properly detected."""
        from detection.mode_detector import ModeDetector

        detector = ModeDetector()

        ja4t_sites = [
            "https://www.linkedin.com/jobs",
            "https://www.amazon.com/dp/B08N5WRWNW",
            "https://www.facebook.com/page",
        ]

        for url in ja4t_sites:
            profile = await detector.detect(url)
            assert profile.uses_ja4t is True, f"JA4T not detected for {url}"
            assert profile.recommended_tier >= 2, f"Tier too low for {url}"

    @pytest.mark.asyncio
    async def test_ja4t_skip_tier1_logic(self):
        """JA4T detection properly skips tier 1."""
        from detection.mode_detector import ModeDetector

        detector = ModeDetector()

        profile = await detector.detect("https://www.linkedin.com/in/test")

        assert profile.uses_ja4t is True
        assert "ja4t_skip_tier1" in profile.metadata
        assert profile.recommended_tier >= 2

    @pytest.mark.asyncio
    async def test_non_ja4t_sites_not_flagged(self):
        """Regular sites don't get JA4T flag."""
        from detection.mode_detector import ModeDetector

        detector = ModeDetector()

        regular_sites = [
            "https://example.com",
            "https://httpbin.org/get",
        ]

        for url in regular_sites:
            profile = await detector.detect(url)
            # Unknown sites should not have JA4T flag
            assert profile.uses_ja4t is False or profile.ja4t_confidence < 0.5


@pytest.mark.e2e
class TestStatisticalBehavior:
    """Statistical tests for behavior simulation."""

    def test_browser_selection_distribution(self):
        """Browser selection roughly follows market share."""
        from fingerprint.manager import BROWSER_MARKET_SHARE
        import random

        # Simulate weighted selection
        def select_browser_weighted(geo: str) -> str:
            shares = BROWSER_MARKET_SHARE.get(geo, BROWSER_MARKET_SHARE["us"])
            browsers = list(shares.keys())
            weights = list(shares.values())
            return random.choices(browsers, weights=weights, k=1)[0]

        # Run 10000 selections for US
        selections = [select_browser_weighted('us') for _ in range(10000)]

        # Count occurrences
        counts = {b: selections.count(b) for b in ['chrome', 'safari', 'edge', 'firefox']}

        # Chrome should dominate (~65%)
        chrome_pct = counts['chrome'] / 10000
        assert 0.55 < chrome_pct < 0.75, f"Chrome at {chrome_pct:.1%}"

        # Safari should be significant (~20%)
        safari_pct = counts['safari'] / 10000
        assert 0.12 < safari_pct < 0.28, f"Safari at {safari_pct:.1%}"

    def test_typing_delays_gaussian_distribution(self):
        """Typing delays follow approximately Gaussian distribution."""
        from behavior.human import HumanTyping

        # Collect many samples for same character
        delays = [HumanTyping.get_inter_key_delay('a', '') for _ in range(1000)]

        # Check distribution properties
        mean = statistics.mean(delays)
        stdev = statistics.stdev(delays)

        # Most values should be within 2 standard deviations
        within_2sd = sum(1 for d in delays if abs(d - mean) < 2 * stdev)
        pct_within_2sd = within_2sd / 1000

        # For normal distribution, ~95% should be within 2 SD
        # We're more lenient due to the thinking pauses
        assert pct_within_2sd > 0.85, f"Only {pct_within_2sd:.1%} within 2 SD"


@pytest.mark.e2e
class TestProxyCorrelation:
    """E2E tests for proxy-fingerprint correlation."""

    def test_geo_timezone_correlation(self, mock_config, monkeypatch):
        """Proxy geo and timezone are properly correlated."""
        from proxy.manager import GEO_PROFILES

        # Check correlations
        assert GEO_PROFILES["us"]["timezone"] == "America/New_York"
        assert GEO_PROFILES["de"]["timezone"] == "Europe/Berlin"
        assert GEO_PROFILES["jp"]["timezone"] == "Asia/Tokyo"

        # Locale should match
        assert GEO_PROFILES["de"]["locale"] == "de-DE"
        assert GEO_PROFILES["jp"]["locale"] == "ja-JP"

    def test_correlated_headers_match_proxy(self, mock_config, monkeypatch):
        """HTTP headers correlate with proxy configuration."""
        from core.config import ScraperConfig
        from core import config as config_module

        mock_cfg = ScraperConfig(
            proxy_username="test",
            proxy_password="test",
        )
        config_module._config = mock_cfg

        from proxy.manager import ProxyEmpireManager

        manager = ProxyEmpireManager()
        config = manager.get_proxy(geo="de")
        headers = manager.get_correlated_headers(config)

        # Headers should match German locale
        assert "de" in headers["Accept-Language"].lower()

        # User-Agent should be set
        assert len(headers["User-Agent"]) > 20


@pytest.mark.e2e
class TestSessionFingerprint:
    """E2E tests for session-fingerprint integration."""

    def test_session_stores_fingerprint_id(self, session_manager, fingerprint_manager):
        """Sessions correctly store fingerprint IDs."""
        # Get fingerprint
        fp = fingerprint_manager.get_or_create("session-fp-test.com", "us")

        # Create session with fingerprint
        from session.manager import SessionState
        session = SessionState(
            session_id="fp-session",
            fingerprint_id=fp.fingerprint_id
        )
        session_manager.save(session)

        # Load and verify
        loaded = session_manager.get("fp-session")
        assert loaded.fingerprint_id == fp.fingerprint_id

    def test_fingerprint_persists_through_session_reuse(self, session_manager, fingerprint_manager):
        """Fingerprint ID persists when session is reused."""
        domain = "reuse-test.com"
        fp = fingerprint_manager.get_or_create(domain, "us")

        # Create session
        session1 = session_manager.create("reuse-session", url=f"https://{domain}")
        session1.fingerprint_id = fp.fingerprint_id
        session_manager.save(session1)

        # Get same session later
        session2 = session_manager.get_or_create("reuse-session")

        # Should have same fingerprint
        assert session2.fingerprint_id == fp.fingerprint_id

        # And fingerprint should still be valid
        fp2 = fingerprint_manager.get_for_domain(domain)
        assert fp2.fingerprint_id == fp.fingerprint_id
