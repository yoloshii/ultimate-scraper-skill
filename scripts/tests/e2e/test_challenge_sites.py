"""End-to-end tests against real challenge sites.

These tests require network access and may be slow.
Use pytest -m e2e to run them.
"""

import pytest
import sys
import asyncio
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.e2e
class TestPracticeSites:
    """Tests against practice sites that are designed for scraping."""

    @pytest.mark.asyncio
    async def test_httpbin_headers(self):
        """https://httpbin.org/headers returns our User-Agent."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://httpbin.org/headers",
                headers={"User-Agent": "ultimate-scraper-test/1.0"}
            )

            assert response.status_code == 200
            data = response.json()
            assert "ultimate-scraper-test" in data["headers"]["User-Agent"]

    @pytest.mark.asyncio
    async def test_httpbin_ip(self):
        """https://httpbin.org/ip returns an IP address."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("https://httpbin.org/ip")

            assert response.status_code == 200
            data = response.json()
            assert "origin" in data
            # Should be a valid IP format
            assert "." in data["origin"] or ":" in data["origin"]

    @pytest.mark.asyncio
    async def test_books_toscrape_static(self):
        """https://books.toscrape.com/ has extractable content."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("https://books.toscrape.com/")

            assert response.status_code == 200
            html = response.text

            # Should have book listings
            assert "product_pod" in html or "Books to Scrape" in html
            assert "<article" in html

    @pytest.mark.asyncio
    async def test_quotes_toscrape(self):
        """https://quotes.toscrape.com/ has quote content."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("https://quotes.toscrape.com/")

            assert response.status_code == 200
            html = response.text

            # Should have quotes
            assert "quote" in html.lower()
            assert "author" in html.lower()


@pytest.mark.e2e
@pytest.mark.slow
class TestDetectionSites:
    """Tests against bot detection test sites."""

    @pytest.mark.asyncio
    async def test_sannysoft_accessible(self):
        """https://bot.sannysoft.com/ is accessible."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get("https://bot.sannysoft.com/")

            assert response.status_code == 200
            # This page has detection checks
            assert "webdriver" in response.text.lower() or "navigator" in response.text.lower()

    @pytest.mark.asyncio
    async def test_nowsecure_challenge(self):
        """https://nowsecure.nl/ presents Cloudflare challenge."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get("https://nowsecure.nl/")

                # May get blocked or challenged
                if response.status_code == 200:
                    # Check if we got actual content or challenge
                    if "Just a moment" in response.text:
                        pytest.skip("Cloudflare challenge detected (expected for HTTP client)")
                    else:
                        assert len(response.text) > 100
                elif response.status_code == 403:
                    pytest.skip("Blocked by Cloudflare (expected for HTTP client)")
            except Exception as e:
                pytest.skip(f"Connection issue: {e}")

    @pytest.mark.asyncio
    async def test_incolumitas_accessible(self):
        """https://bot.incolumitas.com/ is accessible."""
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                response = await client.get("https://bot.incolumitas.com/")

                # Should be accessible
                assert response.status_code in [200, 403]
            except Exception as e:
                pytest.skip(f"Connection issue: {e}")


@pytest.mark.e2e
class TestStaticDataExtraction:
    """Tests for static data extraction from real sites."""

    @pytest.mark.asyncio
    async def test_json_placeholder_api(self):
        """JSONPlaceholder API returns valid JSON."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("https://jsonplaceholder.typicode.com/posts/1")

            assert response.status_code == 200
            data = response.json()
            assert "userId" in data
            assert "title" in data
            assert "body" in data

    @pytest.mark.asyncio
    async def test_dummyjson_products(self):
        """DummyJSON products API returns product data."""
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("https://dummyjson.com/products/1")

            assert response.status_code == 200
            data = response.json()
            assert "title" in data
            assert "price" in data


@pytest.mark.e2e
class TestModeDetection:
    """Tests for mode detection on real sites."""

    @pytest.mark.asyncio
    async def test_detect_github(self):
        """GitHub detection works."""
        from detection.mode_detector import ModeDetector

        detector = ModeDetector()
        profile = await detector.detect("https://github.com/microsoft/TypeScript")

        # GitHub should not require heavy anti-bot measures
        assert profile.recommended_tier <= 2

    @pytest.mark.asyncio
    async def test_detect_amazon(self):
        """Amazon detection identifies antibot."""
        from detection.mode_detector import ModeDetector

        detector = ModeDetector()
        profile = await detector.detect("https://www.amazon.com/dp/B08N5WRWNW")

        assert profile.antibot == "akamai"
        assert profile.uses_ja4t is True
        assert profile.recommended_tier >= 3

    @pytest.mark.asyncio
    async def test_detect_linkedin(self):
        """LinkedIn detection identifies JA4T."""
        from detection.mode_detector import ModeDetector

        detector = ModeDetector()
        profile = await detector.detect("https://www.linkedin.com/company/google")

        assert profile.antibot == "datadome"
        assert profile.uses_ja4t is True
        assert profile.ja4t_confidence >= 0.9


@pytest.mark.e2e
class TestPaywallDetection:
    """Tests for paywall detection patterns."""

    def test_detect_paywall_patterns(self):
        """PaywallDetector identifies common patterns."""
        from detection.paywall_detector import PaywallDetector

        detector = PaywallDetector()

        # Test various paywall HTML patterns
        paywall_samples = [
            "<div>Subscribe to continue reading this article.</div>",
            "<p>You have reached your free limit.</p>",  # Pattern: you('ve| have) (reached|hit) your (free |monthly )?limit
            "<h2>This content is for premium subscribers only.</h2>",
            "<div>Start your free trial to access this content.</div>",
        ]

        for sample in paywall_samples:
            restriction = detector.detect(sample)
            assert restriction is not None, f"Failed to detect: {sample}"
            assert restriction.type == "paywall"

    def test_no_false_positives(self):
        """Normal content doesn't trigger false positives."""
        from detection.paywall_detector import PaywallDetector

        detector = PaywallDetector()

        normal_samples = [
            "<html><body><h1>Welcome to our blog</h1><p>This is a free article about technology.</p></body></html>",
            "<html><body><article><h1>News Story</h1><p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore.</p></article></body></html>",
        ]

        for sample in normal_samples:
            restriction = detector.detect(sample)
            assert restriction is None, f"False positive on: {sample[:50]}..."
