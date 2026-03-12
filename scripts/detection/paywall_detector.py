"""Paywall and access restriction detection."""

import re
from dataclasses import dataclass
from typing import Optional, Literal


@dataclass
class AccessRestriction:
    """Detected access restriction."""

    type: Literal["paywall", "captcha", "captcha_unsolvable", "geo_restricted", "login_required", "content_blocked", "not_found", "all_tiers_failed"]
    pattern: Optional[str] = None
    confidence: float = 0.8
    message: Optional[str] = None


class PaywallDetector:
    """Detect paywall and access restriction patterns."""

    # Soft paywall patterns (article limits)
    SOFT_PAYWALL_PATTERNS = [
        r"subscribe to (continue|read|access)",
        r"you('ve| have) (reached|hit) your (free |monthly )?limit",
        r"(sign up|register|log ?in) to (continue|read|access)",
        r"this (article|content) is for (subscribers|members|premium)",
        r"(unlock|access) (this|full) (article|story|content)",
        r"free articles? remaining",
        r"you have \d+ free articles? left",
        r"create (a )?free account",
    ]

    # Hard paywall patterns (subscription required)
    HARD_PAYWALL_PATTERNS = [
        r"subscription required",
        r"premium (content|article|access)",
        r"members[- ]only",
        r"exclusive (content|access)",
        r"paid subscribers? only",
        r"upgrade to (premium|pro|plus)",
        r"start your (free )?trial",
    ]

    # CAPTCHA patterns
    CAPTCHA_PATTERNS = [
        r"g-recaptcha",
        r"recaptcha/api",
        r"grecaptcha",
        r"hcaptcha",
        r"h-captcha",
        r"captcha",
        r"verify you('re| are) (human|not a robot)",
        r"prove you('re| are) human",
        r"security check",
        r"challenge-platform",
    ]

    # Geo-restriction patterns
    GEO_PATTERNS = [
        r"(not |un)available in your (region|country|location)",
        r"this (content|service) is (not |un)available",
        r"access (denied|blocked) (from|in) your (location|country)",
        r"geo[- ]?restricted",
        r"not available in your area",
        r"content is blocked in your country",
    ]

    # Login required patterns (informational only - not actionable for stealth scraping)
    LOGIN_PATTERNS = [
        r"(please )?(log ?in|sign ?in) to (view|access|continue)",
        r"you must be (logged in|signed in)",
        r"login required",
        r"authentication required",
        r"create an account to",
    ]

    # Cookie consent patterns (not a restriction, just noise)
    COOKIE_PATTERNS = [
        r"accept (cookies|our policy) to continue",
        r"we (use|need) cookies",
        r"cookie (policy|consent|notice)",
    ]

    # 404 Not Found patterns (not actionable - page doesn't exist)
    NOT_FOUND_PATTERNS = [
        r"404",
        r"page not found",
        r"not found",
        r"page (does not|doesn't) exist",
        r"(this |the )?page (is |has been )?(missing|removed|deleted)",
        r"(we )?(can't|cannot|couldn't) find (this|the|that) page",
        r"(sorry|oops)[,!]? (we )?(can't|cannot|couldn't) find",
        r"nothing (here|found)",
        r"no longer (exists|available)",
        r"link (is |may be )?(broken|incorrect)",
        r"url (is |may be )?(incorrect|wrong)",
    ]

    def detect(self, html: str, status_code: int = 200) -> Optional[AccessRestriction]:
        """
        Detect access restrictions in response.

        Args:
            html: Response HTML content
            status_code: HTTP status code

        Returns:
            AccessRestriction if detected, None otherwise
        """
        html_lower = html.lower()

        # Check for 404 Not Found first (not actionable - page doesn't exist)
        # This prevents minimal content on 404 pages from triggering content_blocked
        if status_code == 404:
            return AccessRestriction(
                type="not_found",
                pattern="http_404",
                confidence=0.99,
                message="Page not found (HTTP 404)"
            )

        # Also detect 404s by content patterns (some servers return 200 with 404 content)
        for pattern in self.NOT_FOUND_PATTERNS:
            if re.search(pattern, html_lower):
                # Check if it's really a 404 page vs just containing "404" incidentally
                # Require pattern match + short content or explicit "page not found" messaging
                text_content = re.sub(r'<[^>]+>', '', html)
                text_content = re.sub(r'\s+', ' ', text_content).strip()

                # Strong 404 indicators
                strong_404 = any(p in html_lower for p in [
                    "page not found", "404", "doesn't exist", "does not exist",
                    "cannot find", "can't find", "no longer exists"
                ])

                # If strong indicator found and content is relatively short, it's a 404
                if strong_404 and len(text_content) < 2000:
                    return AccessRestriction(
                        type="not_found",
                        pattern=pattern,
                        confidence=0.85,
                        message="Page appears to not exist"
                    )

        # Check for CAPTCHA first (highest priority)
        # All CAPTCHAs are reported as "captcha" — the orchestrator decides
        # solvability at runtime based on configured solver keys.
        for pattern in self.CAPTCHA_PATTERNS:
            if re.search(pattern, html_lower):
                captcha_detail = None
                if "recaptcha" in html_lower and "v3" in html_lower:
                    captcha_detail = "reCAPTCHA v3 detected"
                elif "recaptcha" in html_lower:
                    captcha_detail = "reCAPTCHA v2 detected"
                elif "hcaptcha" in html_lower:
                    captcha_detail = "hCaptcha detected"
                elif "turnstile" in html_lower or "challenges.cloudflare" in html_lower:
                    captcha_detail = "Cloudflare Turnstile detected"
                return AccessRestriction(
                    type="captcha",
                    pattern=pattern,
                    confidence=0.85,
                    message=captcha_detail,
                )

        # Check for hard paywall
        for pattern in self.HARD_PAYWALL_PATTERNS:
            if re.search(pattern, html_lower):
                return AccessRestriction(
                    type="paywall",
                    pattern=pattern,
                    confidence=0.9,
                    message="Subscription required"
                )

        # Check for soft paywall
        for pattern in self.SOFT_PAYWALL_PATTERNS:
            if re.search(pattern, html_lower):
                return AccessRestriction(
                    type="paywall",
                    pattern=pattern,
                    confidence=0.8,
                    message="Article limit or signup required"
                )

        # Check for geo-restriction
        for pattern in self.GEO_PATTERNS:
            if re.search(pattern, html_lower):
                return AccessRestriction(
                    type="geo_restricted",
                    pattern=pattern,
                    confidence=0.85,
                )

        # Check for login required
        for pattern in self.LOGIN_PATTERNS:
            if re.search(pattern, html_lower):
                return AccessRestriction(
                    type="login_required",
                    pattern=pattern,
                    confidence=0.8,
                )

        # Check for minimal content (possible soft block)
        # Only trigger if HTML is very small AND has almost no text content
        # Skip this check for JSON responses (valid API responses are often small)
        stripped = html.strip()
        if len(stripped) < 500 and status_code == 200:
            # Skip if it looks like valid JSON
            if stripped.startswith("{") or stripped.startswith("["):
                pass  # Valid JSON response, not blocked
            # Check if it's wrapped HTML with minimal content
            elif "<html" in html_lower and "</html>" in html_lower:
                # Extract text content (strip all tags)
                text_content = re.sub(r'<[^>]+>', '', html)
                text_content = re.sub(r'\s+', ' ', text_content).strip()
                # Skip if the text content looks like JSON
                if text_content.startswith("{") or text_content.startswith("["):
                    pass  # JSON wrapped in HTML tags
                # Only flag if text content is also very minimal (< 50 chars) and not JSON-like
                elif len(text_content) < 50:
                    return AccessRestriction(
                        type="content_blocked",
                        pattern="minimal_content",
                        confidence=0.6,
                        message="Page returned minimal content"
                    )

        # Check HTTP status codes
        if status_code == 402:
            return AccessRestriction(
                type="paywall",
                pattern="http_402",
                confidence=0.95,
                message="Payment Required (HTTP 402)"
            )
        if status_code == 403:
            # Only flag 403 as blocked if it's a real anti-bot block
            # Test pages and informational 403s with meaningful content should pass through
            if self._is_real_block(html):
                return AccessRestriction(
                    type="content_blocked",
                    pattern="http_403",
                    confidence=0.9,
                    message="Access Forbidden (HTTP 403)"
                )
        if status_code == 451:
            return AccessRestriction(
                type="geo_restricted",
                pattern="http_451",
                confidence=0.95,
                message="Unavailable For Legal Reasons (HTTP 451)"
            )

        return None

    def _is_real_block(self, html: str) -> bool:
        """
        Check if response is a real anti-bot block vs test/informational page.

        Returns True if it looks like a real block.
        Returns False if it has meaningful content (test page, API error, etc.)
        """
        if not html:
            return True  # Empty response is a block

        # Extract text content
        text_content = re.sub(r'<[^>]+>', '', html)
        text_content = re.sub(r'\s+', ' ', text_content).strip()

        # Short responses with no real content are blocks
        if len(text_content) < 50:
            return True

        html_lower = html.lower()
        text_lower = text_content.lower()

        # Strong indicators of actual anti-bot block
        block_indicators = [
            "access denied",
            "blocked by",
            "bot detected",
            "automated access",
            "suspicious activity",
            "security check",
            "please verify you are human",
            "enable javascript and cookies",
            "your ip has been",
            "request blocked",
        ]

        # Indicators that it's a test/informational page, not a real block
        test_indicators = [
            "test",
            "example",
            "scraper",
            "crawl",
            "status code",
            "http 403",
            "403 forbidden",
            "demonstration",
            "testing",
        ]

        has_block_indicator = any(ind in text_lower for ind in block_indicators)
        has_test_indicator = any(ind in text_lower for ind in test_indicators)

        # If it looks like a test page, it's not a real block
        if has_test_indicator:
            return False

        # If it has block indicators without test indicators, it's a real block
        if has_block_indicator:
            return True

        # Meaningful content (>200 chars) without block indicators = not a block
        if len(text_content) > 200:
            return False

        # Default: uncertain, assume not a block for short content
        return False

    def is_paywall(self, html: str) -> bool:
        """Quick check if content has a paywall."""
        restriction = self.detect(html)
        return restriction is not None and restriction.type == "paywall"

    def is_captcha(self, html: str) -> bool:
        """Quick check if content has a CAPTCHA."""
        restriction = self.detect(html)
        return restriction is not None and restriction.type in ["captcha", "captcha_unsolvable"]

    def is_not_found(self, html: str, status_code: int = 200) -> bool:
        """Quick check if page is a 404 Not Found."""
        restriction = self.detect(html, status_code)
        return restriction is not None and restriction.type == "not_found"

    def needs_brightdata(self, restriction: Optional[AccessRestriction]) -> bool:
        """
        Check if restriction type should trigger Brightdata fallback.

        Brightdata Web Unlocker is used for:
        - Paywalls (soft and hard)
        - Complex CAPTCHAs (reCAPTCHA v3)
        - Geo-restrictions (as last resort)
        """
        if restriction is None:
            return False

        return restriction.type in [
            "paywall",
            "geo_restricted",
            "content_blocked",
            "all_tiers_failed",
        ]

    def get_fallback_recommendation(self, restriction: AccessRestriction) -> dict:
        """
        Get recommendation for handling the restriction.

        Returns:
            Dict with recommended action and details
        """
        recommendations = {
            "paywall": {
                "action": "brightdata",
                "message": "Try Brightdata Web Unlocker for paywall bypass",
            },
            "captcha": {
                "action": "escalate",
                "message": "Escalate to Tier 3 (Camoufox) for CAPTCHA handling",
            },
            "captcha_unsolvable": {
                "action": "brightdata",
                "message": "Complex CAPTCHA - use Brightdata Web Unlocker",
            },
            "geo_restricted": {
                "action": "proxy_geo",
                "message": "Try different proxy geo-location",
            },
            "login_required": {
                "action": "none",  # Informational only - not actionable for stealth scraping
                "message": "Login required (content may be limited)",
            },
            "content_blocked": {
                "action": "brightdata",
                "message": "Content blocked - try Brightdata Web Unlocker",
            },
            "not_found": {
                "action": "none",
                "message": "Page does not exist (404) - no fallback available",
            },
            "all_tiers_failed": {
                "action": "brightdata",
                "message": "All tiers exhausted - final Brightdata attempt",
            },
        }

        return recommendations.get(restriction.type, {
            "action": "retry",
            "message": "Unknown restriction - retry with higher tier",
        })
