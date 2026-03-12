"""Unit tests for ScrapeResult and exceptions."""

import pytest
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from core.result import (
    ScrapeResult,
    ScrapeError,
    Blocked,
    CaptchaRequired,
    CaptchaUnsolvable,
    PaywallDetected,
    GeoRestricted,
    RateLimited,
    SessionExpired,
    ProxyError,
    ContentEmpty,
)


class TestScrapeResult:
    """Tests for ScrapeResult dataclass."""

    def test_scrape_result_defaults(self):
        """ScrapeResult has sensible defaults."""
        result = ScrapeResult()

        assert result.success is False
        assert result.tier_used == -1
        assert result.status_code == 0
        assert result.html == ""
        assert result.markdown == ""
        assert result.error is None
        assert result.cookies == {}

    def test_scrape_result_content_property_markdown(self):
        """content property returns markdown when available."""
        result = ScrapeResult(
            html="<html>HTML content</html>",
            markdown="# Markdown content",
            raw="raw content"
        )

        assert result.content == "# Markdown content"

    def test_scrape_result_content_property_html(self):
        """content property returns HTML when no markdown."""
        result = ScrapeResult(
            html="<html>HTML content</html>",
            markdown="",
            raw="raw content"
        )

        assert result.content == "<html>HTML content</html>"

    def test_scrape_result_content_property_raw(self):
        """content property returns raw when no markdown or HTML."""
        result = ScrapeResult(
            html="",
            markdown="",
            raw="raw content"
        )

        assert result.content == "raw content"

    def test_scrape_result_to_dict(self):
        """to_dict() serializes all fields."""
        result = ScrapeResult(
            success=True,
            tier_used=2,
            status_code=200,
            url="https://example.com",
            final_url="https://example.com/redirected",
            html="<html>content</html>",
            markdown="# Content",
            extracted_data={"key": "value"},
            session_id="test-session",
            fingerprint_id="fp-123",
        )

        d = result.to_dict()

        assert d["success"] is True
        assert d["tier_used"] == 2
        assert d["status_code"] == 200
        assert d["url"] == "https://example.com"
        assert d["final_url"] == "https://example.com/redirected"
        assert d["extracted_data"] == {"key": "value"}
        assert d["session_id"] == "test-session"
        assert d["fingerprint_id"] == "fp-123"

    def test_scrape_result_to_dict_content_length(self):
        """to_dict() includes content_length."""
        result = ScrapeResult(
            markdown="# Hello World"
        )

        d = result.to_dict()

        assert d["content_length"] == len("# Hello World")

    def test_scrape_result_formatted_output_markdown(self):
        """formatted_output returns markdown when available."""
        result = ScrapeResult(
            markdown="# Markdown Output"
        )

        assert result.formatted_output == "# Markdown Output"

    def test_scrape_result_formatted_output_truncated_html(self):
        """formatted_output truncates long HTML."""
        long_html = "<html>" + "x" * 15000 + "</html>"
        result = ScrapeResult(
            html=long_html,
            markdown=""
        )

        output = result.formatted_output
        assert len(output) < len(long_html)
        assert output.endswith("...")

    def test_scrape_result_formatted_output_raw(self):
        """formatted_output returns raw when no HTML or markdown."""
        result = ScrapeResult(
            raw="raw output only"
        )

        assert result.formatted_output == "raw output only"

    def test_scrape_result_str_success(self):
        """__str__ shows success info."""
        result = ScrapeResult(
            success=True,
            tier_used=3,
            markdown="# Content"
        )

        s = str(result)
        assert "success=True" in s
        assert "tier=3" in s

    def test_scrape_result_str_failure(self):
        """__str__ shows error info."""
        result = ScrapeResult(
            success=False,
            error="Connection timeout"
        )

        s = str(result)
        assert "success=False" in s
        assert "Connection timeout" in s

    def test_scrape_result_with_screenshot(self):
        """ScrapeResult stores screenshot data."""
        result = ScrapeResult(
            screenshot_base64="base64encodedimage...",
            screenshot_path="/path/to/screenshot.png"
        )

        assert result.screenshot_base64 == "base64encodedimage..."
        assert result.screenshot_path == "/path/to/screenshot.png"

    def test_scrape_result_with_vision_extraction(self):
        """ScrapeResult stores vision extraction result."""
        result = ScrapeResult(
            vision_extraction={"heading": "Test", "price": "$19.99"}
        )

        assert result.vision_extraction == {"heading": "Test", "price": "$19.99"}

    def test_scrape_result_with_static_data(self):
        """ScrapeResult stores static data extraction."""
        result = ScrapeResult(
            static_data={"next_data": {"props": {}}}
        )

        assert result.static_data == {"next_data": {"props": {}}}

    def test_scrape_result_with_fingerprint_id(self):
        """ScrapeResult stores fingerprint ID."""
        result = ScrapeResult(
            fingerprint_id="fp-abc123"
        )

        assert result.fingerprint_id == "fp-abc123"


class TestScrapeExceptions:
    """Tests for custom scraper exceptions."""

    def test_exception_inheritance(self):
        """All custom exceptions inherit from ScraperError."""
        assert issubclass(Blocked, ScrapeError)
        assert issubclass(CaptchaRequired, ScrapeError)
        assert issubclass(CaptchaUnsolvable, ScrapeError)
        assert issubclass(PaywallDetected, ScrapeError)
        assert issubclass(GeoRestricted, ScrapeError)
        assert issubclass(RateLimited, ScrapeError)
        assert issubclass(SessionExpired, ScrapeError)
        assert issubclass(ProxyError, ScrapeError)
        assert issubclass(ContentEmpty, ScrapeError)

    def test_scrape_error_is_exception(self):
        """ScraperError is an Exception subclass."""
        assert issubclass(ScrapeError, Exception)

    def test_blocked_exception(self):
        """Blocked exception can be raised and caught."""
        with pytest.raises(Blocked):
            raise Blocked("Access blocked by anti-bot")

    def test_captcha_required_exception(self):
        """CaptchaRequired exception can be raised."""
        with pytest.raises(CaptchaRequired):
            raise CaptchaRequired("CAPTCHA challenge detected")

    def test_captcha_unsolvable_exception(self):
        """CaptchaUnsolvable exception can be raised."""
        with pytest.raises(CaptchaUnsolvable):
            raise CaptchaUnsolvable("reCAPTCHA v3 detected")

    def test_paywall_detected_exception(self):
        """PaywallDetected exception can be raised."""
        with pytest.raises(PaywallDetected):
            raise PaywallDetected("Subscription required")

    def test_geo_restricted_exception(self):
        """GeoRestricted exception can be raised."""
        with pytest.raises(GeoRestricted):
            raise GeoRestricted("Content not available in your region")

    def test_rate_limited_exception(self):
        """RateLimited exception can be raised."""
        with pytest.raises(RateLimited):
            raise RateLimited("Too many requests")

    def test_session_expired_exception(self):
        """SessionExpired exception can be raised."""
        with pytest.raises(SessionExpired):
            raise SessionExpired("Session token expired")

    def test_proxy_error_exception(self):
        """ProxyError exception can be raised."""
        with pytest.raises(ProxyError):
            raise ProxyError("Proxy connection failed")

    def test_content_empty_exception(self):
        """ContentEmpty exception can be raised."""
        with pytest.raises(ContentEmpty):
            raise ContentEmpty("Page returned empty content")

    def test_exception_message(self):
        """Exception messages are preserved."""
        message = "Custom error message"
        try:
            raise Blocked(message)
        except Blocked as e:
            assert str(e) == message

    def test_catch_scrape_error_catches_all(self):
        """Catching ScrapeError catches all subclasses."""
        exceptions = [
            Blocked("blocked"),
            CaptchaRequired("captcha"),
            PaywallDetected("paywall"),
            GeoRestricted("geo"),
            RateLimited("rate"),
            ProxyError("proxy"),
            ContentEmpty("empty"),
        ]

        for exc in exceptions:
            with pytest.raises(ScrapeError):
                raise exc
