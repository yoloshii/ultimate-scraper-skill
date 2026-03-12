"""Unit tests for ModeDetector and ScrapeProfile."""

import pytest
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from detection.mode_detector import ModeDetector, ScrapeProfile, SITE_PROFILES, JA4T_SITES


class TestScrapeProfile:
    """Tests for ScrapeProfile dataclass."""

    def test_scrape_profile_defaults(self):
        """Default profile has tier 1, no antibot, no JA4T."""
        profile = ScrapeProfile(url="https://example.com")

        assert profile.recommended_tier == 1
        assert profile.antibot is None
        assert profile.uses_ja4t is False
        assert profile.ja4t_confidence == 0.0
        assert profile.has_static_data is False

    def test_scrape_profile_custom_values(self):
        """ScrapeProfile accepts custom values."""
        profile = ScrapeProfile(
            url="https://amazon.com/product",
            domain="amazon.com",
            antibot="akamai",
            antibot_confidence=0.9,
            uses_ja4t=True,
            ja4t_confidence=0.85,
            recommended_tier=3,
            needs_proxy=True,
        )

        assert profile.antibot == "akamai"
        assert profile.uses_ja4t is True
        assert profile.recommended_tier == 3


class TestModeDetector:
    """Tests for ModeDetector site detection."""

    @pytest.fixture
    def detector(self):
        return ModeDetector()

    @pytest.mark.asyncio
    async def test_detect_known_site_amazon(self, detector):
        """Amazon pattern detected with JA4T flag."""
        profile = await detector.detect("https://www.amazon.com/product/123")

        assert profile.antibot == "akamai"
        assert profile.uses_ja4t is True
        assert profile.recommended_tier >= 3
        assert profile.needs_proxy is True

    @pytest.mark.asyncio
    async def test_detect_known_site_linkedin(self, detector):
        """LinkedIn detected as DataDome with JA4T."""
        profile = await detector.detect("https://www.linkedin.com/in/username")

        assert profile.antibot == "datadome"
        assert profile.uses_ja4t is True
        assert profile.ja4t_confidence >= 0.9

    @pytest.mark.asyncio
    async def test_detect_known_site_github(self, detector):
        """GitHub detected as no antibot, tier 1."""
        profile = await detector.detect("https://github.com/user/repo")

        # GitHub is not in the known list, so defaults
        assert profile.recommended_tier <= 2

    @pytest.mark.asyncio
    async def test_detect_cloudflare_from_headers(self, detector):
        """cf-ray header triggers Cloudflare detection."""
        headers = {
            "cf-ray": "abc123-IAD",
            "cf-cache-status": "HIT",
            "content-type": "text/html",
        }
        profile = await detector.detect(
            "https://example.com",
            headers=headers
        )

        assert profile.antibot == "cloudflare"
        assert profile.antibot_confidence >= 0.7

    @pytest.mark.asyncio
    async def test_detect_datadome_from_headers(self, detector):
        """x-datadome header triggers DataDome detection."""
        headers = {
            "x-datadome": "some-token",
            "content-type": "text/html",
        }
        profile = await detector.detect(
            "https://unknown-site.com",
            headers=headers
        )

        assert profile.antibot == "datadome"

    @pytest.mark.asyncio
    async def test_detect_cloudflare_from_html(self, detector, sample_html_cloudflare):
        """'Just a moment...' in HTML triggers Cloudflare detection."""
        profile = await detector.detect(
            "https://example.com",
            html=sample_html_cloudflare
        )

        assert profile.antibot == "cloudflare"

    @pytest.mark.asyncio
    async def test_detect_akamai_from_html(self, detector):
        """'_abck' cookie in HTML triggers Akamai detection."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><script>
        var _abck = "abc123";
        var bm_sz = "xyz789";
        </script></head>
        <body>Content</body>
        </html>
        """
        profile = await detector.detect(
            "https://unknown-store.com",
            html=html
        )

        assert profile.antibot == "akamai"

    @pytest.mark.asyncio
    async def test_detect_static_data_nextjs(self, detector, sample_html_nextjs):
        """__NEXT_DATA__ triggers has_static_data=True."""
        profile = await detector.detect(
            "https://nextjs-site.com",
            html=sample_html_nextjs
        )

        assert profile.has_static_data is True
        assert profile.detected_framework == "nextjs"

    @pytest.mark.asyncio
    async def test_detect_framework_nextjs(self, detector, sample_html_nextjs):
        """__NEXT_DATA__ detected as 'nextjs' framework."""
        profile = await detector.detect(
            "https://nextjs-site.com",
            html=sample_html_nextjs
        )

        assert profile.detected_framework == "nextjs"

    @pytest.mark.asyncio
    async def test_detect_framework_nuxt(self, detector, sample_html_nuxt):
        """__NUXT__ detected as 'nuxt' framework."""
        profile = await detector.detect(
            "https://nuxt-site.com",
            html=sample_html_nuxt
        )

        assert profile.detected_framework == "nuxt"

    @pytest.mark.asyncio
    async def test_ja4t_detection_linkedin(self, detector):
        """LinkedIn triggers JA4T with high confidence."""
        profile = await detector.detect("https://www.linkedin.com/jobs")

        assert profile.uses_ja4t is True
        assert profile.ja4t_confidence >= 0.9

    @pytest.mark.asyncio
    async def test_ja4t_detection_google_suspected(self, detector):
        """Google triggers JA4T with lower confidence."""
        profile = await detector.detect("https://www.google.com/search")

        assert profile.uses_ja4t is True
        assert profile.ja4t_confidence < 0.9  # Suspected, not confirmed

    @pytest.mark.asyncio
    async def test_ja4t_forces_tier_2_minimum(self, detector):
        """JA4T sites get recommended_tier >= 2."""
        # Sites with JA4T should skip tier 1 (HTTP)
        profile = await detector.detect("https://www.linkedin.com/test")

        assert profile.recommended_tier >= 2
        assert "ja4t_skip_tier1" in profile.metadata

    @pytest.mark.asyncio
    async def test_unknown_site_defaults(self, detector):
        """Unknown sites get default profile."""
        profile = await detector.detect("https://some-random-blog.xyz")

        assert profile.antibot is None
        assert profile.recommended_tier == 1
        assert profile.needs_proxy is False

    @pytest.mark.asyncio
    async def test_static_data_detected(self, detector, sample_html_nextjs):
        """Sites with static data are detected but may not change tier."""
        profile = await detector.detect(
            "https://static-nextjs-blog.com",
            html=sample_html_nextjs
        )

        # Static data should be detected
        assert profile.has_static_data is True
        assert profile.detected_framework == "nextjs"
        # Tier stays at default since detection flow may vary
        assert profile.recommended_tier <= 1


class TestSiteProfiles:
    """Tests for site profiles database."""

    def test_site_profiles_has_default(self):
        """SITE_PROFILES contains _default entry."""
        assert "_default" in SITE_PROFILES
        assert SITE_PROFILES["_default"]["tier"] == 1

    def test_ja4t_sites_have_confidence(self):
        """All JA4T_SITES entries have confidence field."""
        for pattern, config in JA4T_SITES.items():
            assert "confidence" in config
            assert 0 <= config["confidence"] <= 1

    def test_ja4t_patterns_valid(self):
        """JA4T_SITES patterns are valid domain fragments."""
        for pattern in JA4T_SITES.keys():
            # Should be domain-like patterns
            assert "." in pattern or pattern.isalnum()

    def test_known_sites_have_required_fields(self):
        """All SITE_PROFILES have required fields."""
        for pattern, config in SITE_PROFILES.items():
            if pattern == "_default":
                continue
            assert "tier" in config
            assert isinstance(config["tier"], int)
            assert 0 <= config["tier"] <= 5
