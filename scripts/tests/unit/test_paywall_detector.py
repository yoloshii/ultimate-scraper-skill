"""Unit tests for PaywallDetector and AccessRestriction."""

import pytest
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from detection.paywall_detector import PaywallDetector, AccessRestriction


class TestAccessRestriction:
    """Tests for AccessRestriction dataclass."""

    def test_access_restriction_defaults(self):
        """AccessRestriction has default values."""
        restriction = AccessRestriction(type="paywall")

        assert restriction.type == "paywall"
        assert restriction.pattern is None
        assert restriction.confidence == 0.8
        assert restriction.message is None

    def test_access_restriction_custom_values(self):
        """AccessRestriction accepts custom values."""
        restriction = AccessRestriction(
            type="captcha",
            pattern="g-recaptcha",
            confidence=0.95,
            message="CAPTCHA detected"
        )

        assert restriction.type == "captcha"
        assert restriction.pattern == "g-recaptcha"
        assert restriction.confidence == 0.95


class TestPaywallDetector:
    """Tests for PaywallDetector."""

    @pytest.fixture
    def detector(self):
        return PaywallDetector()

    def test_detect_soft_paywall_patterns(self, detector):
        """'subscribe to continue' triggers soft paywall."""
        html = """
        <html>
        <body>
        <h1>Article Title</h1>
        <p>Preview content...</p>
        <div class="paywall">
            <p>Subscribe to continue reading this article.</p>
        </div>
        </body>
        </html>
        """
        restriction = detector.detect(html)

        assert restriction is not None
        assert restriction.type == "paywall"

    def test_detect_hard_paywall_patterns(self, detector):
        """'subscribers only' triggers hard paywall."""
        html = """
        <html>
        <body>
        <h1>Premium Content</h1>
        <div class="premium-wall">
            <p>This content is for paid subscribers only.</p>
        </div>
        </body>
        </html>
        """
        restriction = detector.detect(html)

        assert restriction is not None
        assert restriction.type == "paywall"
        assert restriction.confidence >= 0.9

    def test_detect_captcha_cloudflare(self, detector, sample_html_captcha):
        """Cloudflare challenge detected as CAPTCHA."""
        restriction = detector.detect(sample_html_captcha)

        assert restriction is not None
        assert restriction.type in ["captcha", "captcha_unsolvable"]

    def test_detect_captcha_recaptcha_v3(self, detector):
        """reCAPTCHA v3 detected as unsolvable."""
        html = """
        <html>
        <body>
        <script src="https://www.google.com/recaptcha/api.js?render=v3"></script>
        <div class="g-recaptcha" data-sitekey="abc" data-v3="true"></div>
        </body>
        </html>
        """
        restriction = detector.detect(html)

        # Should detect as captcha (v3 might be unsolvable)
        assert restriction is not None
        assert restriction.type in ["captcha", "captcha_unsolvable"]

    def test_detect_geo_restriction(self, detector):
        """'not available in your region' detected."""
        html = """
        <html>
        <body>
        <h1>Sorry</h1>
        <p>This content is not available in your region.</p>
        </body>
        </html>
        """
        restriction = detector.detect(html)

        assert restriction is not None
        assert restriction.type == "geo_restricted"

    def test_detect_login_required(self, detector):
        """'log in to view' detected."""
        html = """
        <html>
        <body>
        <h1>Private Content</h1>
        <p>Please log in to view this content.</p>
        </body>
        </html>
        """
        restriction = detector.detect(html)

        assert restriction is not None
        assert restriction.type == "login_required"

    def test_minimal_content_detection(self, detector, sample_html_minimal):
        """< 500 chars with no content flagged as blocked."""
        restriction = detector.detect(sample_html_minimal)

        # Minimal content with valid HTML structure
        assert restriction is not None
        assert restriction.type == "content_blocked"

    def test_needs_brightdata_for_hard_paywall(self, detector):
        """Hard paywall returns needs_brightdata=True."""
        restriction = AccessRestriction(
            type="paywall",
            pattern="subscription required",
            confidence=0.9
        )

        assert detector.needs_brightdata(restriction) is True

    def test_needs_brightdata_for_captcha_unsolvable(self, detector):
        """Complex CAPTCHA returns needs_brightdata=True."""
        # E1: captcha_unsolvable no longer triggers Brightdata directly.
        # CAPTCHAs are now handled by the solver first; only if unsolvable
        # AND all tiers fail does Brightdata get triggered via all_tiers_failed.
        restriction = AccessRestriction(
            type="captcha_unsolvable",
            confidence=0.9
        )

        assert detector.needs_brightdata(restriction) is False

    def test_needs_brightdata_for_geo_restricted(self, detector):
        """Geo-restricted content returns needs_brightdata=True."""
        restriction = AccessRestriction(
            type="geo_restricted",
            confidence=0.9
        )

        assert detector.needs_brightdata(restriction) is True

    def test_needs_brightdata_false_for_simple_captcha(self, detector):
        """Simple CAPTCHA returns needs_brightdata=False."""
        restriction = AccessRestriction(
            type="captcha",
            confidence=0.85
        )

        # Regular CAPTCHA should try escalation first
        assert detector.needs_brightdata(restriction) is False

    def test_needs_brightdata_none_restriction(self, detector):
        """None restriction returns needs_brightdata=False."""
        assert detector.needs_brightdata(None) is False

    def test_is_paywall_helper(self, detector):
        """is_paywall() returns True for paywall content."""
        html_paywall = "<html><body>Subscribe to continue reading</body></html>"
        html_normal = "<html><body>Normal content here</body></html>"

        assert detector.is_paywall(html_paywall) is True
        assert detector.is_paywall(html_normal) is False

    def test_is_captcha_helper(self, detector, sample_html_captcha):
        """is_captcha() returns True for CAPTCHA content."""
        html_normal = "<html><body>Normal content here</body></html>"

        assert detector.is_captcha(sample_html_captcha) is True
        assert detector.is_captcha(html_normal) is False

    def test_get_fallback_recommendation_paywall(self, detector):
        """get_fallback_recommendation() returns correct action for paywall."""
        restriction = AccessRestriction(type="paywall")
        rec = detector.get_fallback_recommendation(restriction)

        assert rec["action"] == "brightdata"

    def test_get_fallback_recommendation_captcha(self, detector):
        """get_fallback_recommendation() returns escalate for simple CAPTCHA."""
        restriction = AccessRestriction(type="captcha")
        rec = detector.get_fallback_recommendation(restriction)

        assert rec["action"] == "escalate"

    def test_get_fallback_recommendation_geo(self, detector):
        """get_fallback_recommendation() returns proxy_geo for geo restriction."""
        restriction = AccessRestriction(type="geo_restricted")
        rec = detector.get_fallback_recommendation(restriction)

        assert rec["action"] == "proxy_geo"

    def test_http_402_detected(self, detector):
        """HTTP 402 Payment Required detected as paywall."""
        restriction = detector.detect("<html><body></body></html>", status_code=402)

        assert restriction is not None
        assert restriction.type == "paywall"
        assert restriction.confidence >= 0.9

    def test_http_451_detected(self, detector):
        """HTTP 451 Unavailable For Legal Reasons detected as geo restricted."""
        restriction = detector.detect("<html><body></body></html>", status_code=451)

        assert restriction is not None
        assert restriction.type == "geo_restricted"

    def test_no_false_positive_for_normal_content(self, detector):
        """Normal content doesn't trigger false positives."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Blog Post</title></head>
        <body>
        <h1>Welcome to My Blog</h1>
        <p>This is a regular blog post with plenty of content.</p>
        <p>Here is another paragraph with more information about the topic.</p>
        <p>And even more content to make this a substantial page.</p>
        <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
        </body>
        </html>
        """
        restriction = detector.detect(html)

        assert restriction is None

    def test_json_response_not_blocked(self, detector):
        """Valid JSON response is not flagged as blocked."""
        json_response = '{"data": {"items": [1, 2, 3]}, "status": "ok"}'
        restriction = detector.detect(json_response)

        assert restriction is None
