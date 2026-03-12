"""Site profile detection for optimal tier selection."""

import re
from dataclasses import dataclass, field
from typing import Optional, Literal
from urllib.parse import urlparse


@dataclass
class ScrapeProfile:
    """Profile describing site characteristics and recommended scraping approach."""

    url: str
    domain: str = ""

    # Anti-bot detection
    antibot: Optional[str] = None  # cloudflare, cloudflare_uam, akamai, datadome, perimeterx, etc.
    antibot_confidence: float = 0.0

    # JA4T (Transport-layer fingerprinting) detection
    uses_ja4t: bool = False         # Site uses JA4T detection
    ja4t_confidence: float = 0.0    # Confidence level (0-1)

    # Content characteristics
    has_static_data: bool = False
    requires_js: bool = False
    requires_login: bool = False

    # Recommended approach
    recommended_tier: int = 1
    needs_proxy: bool = False
    needs_sticky: bool = False

    # Sensitive site detection (E9)
    is_sensitive: bool = False

    # Additional info
    detected_framework: Optional[str] = None  # nextjs, nuxt, remix, etc.
    metadata: dict = field(default_factory=dict)


# Known site patterns
# ja4t: True indicates the site uses transport-layer (JA4T) fingerprinting
# which detects bots even with perfect JA3 impersonation
SITE_PROFILES = {
    # E-commerce (typically heavy anti-bot with JA4T)
    "amazon.": {"antibot": "akamai", "tier": 3, "proxy": True, "sticky": True, "ja4t": True},
    "ebay.": {"antibot": "akamai", "tier": 3, "proxy": True, "ja4t": True},
    "walmart.": {"antibot": "perimeterx", "tier": 3, "proxy": True, "ja4t": True},
    "target.": {"antibot": "akamai", "tier": 3, "proxy": True, "ja4t": True},
    "bestbuy.": {"antibot": "akamai", "tier": 3, "proxy": True, "ja4t": True},

    # Social media (varies, some with JA4T)
    "linkedin.": {"antibot": "datadome", "tier": 3, "proxy": True, "sticky": True, "ja4t": True},
    "twitter.": {"antibot": "cloudflare", "tier": 2, "proxy": True},
    "x.com": {"antibot": "cloudflare", "tier": 2, "proxy": True},
    "facebook.": {"antibot": "custom", "tier": 3, "proxy": True, "ja4t": True},
    "instagram.": {"antibot": "custom", "tier": 3, "proxy": True, "ja4t": True},

    # Tech/Reviews
    "g2.com": {"antibot": "datadome", "tier": 3, "proxy": True, "ja4t": True},
    "trustpilot.": {"antibot": "cloudflare", "tier": 2, "proxy": True},
    "glassdoor.": {"antibot": "cloudflare", "tier": 2, "proxy": True},

    # Travel (heavy JA4T)
    "booking.com": {"antibot": "perimeterx", "tier": 3, "proxy": True, "ja4t": True},
    "airbnb.": {"antibot": "akamai", "tier": 3, "proxy": True, "ja4t": True},
    "expedia.": {"antibot": "akamai", "tier": 3, "proxy": True, "ja4t": True},

    # Real estate
    "zillow.": {"antibot": "perimeterx", "tier": 3, "proxy": True, "ja4t": True},
    "redfin.": {"antibot": "cloudflare", "tier": 2, "proxy": True},
    "realtor.": {"antibot": "akamai", "tier": 3, "proxy": True},

    # Job boards
    "indeed.": {"antibot": "cloudflare", "tier": 2, "proxy": True},
    "monster.": {"antibot": "cloudflare", "tier": 2, "proxy": True},

    # News (often paywalled)
    "nytimes.": {"antibot": "cloudflare", "tier": 2, "paywall": True},
    "wsj.": {"antibot": "akamai", "tier": 2, "paywall": True},
    "bloomberg.": {"antibot": "cloudflare", "tier": 2, "paywall": True},

    # Google services (suspected JA4T)
    "google.": {"antibot": "custom", "tier": 2, "proxy": True, "ja4t_suspected": True},
    "youtube.": {"antibot": "custom", "tier": 2, "proxy": True, "ja4t_suspected": True},

    # Financial (heavy security)
    "paypal.": {"antibot": "custom", "tier": 3, "proxy": True, "sticky": True, "ja4t": True},
    "chase.": {"antibot": "akamai", "tier": 3, "proxy": True, "sticky": True, "ja4t": True},
    "bankofamerica.": {"antibot": "akamai", "tier": 3, "proxy": True, "sticky": True, "ja4t": True},

    # Default for unknown sites
    "_default": {"antibot": None, "tier": 1, "proxy": False, "ja4t": False},
}

# Sensitive domains requiring rate limiting, fingerprint lock, and behavior boost (E9)
SENSITIVE_DOMAINS = frozenset({
    "linkedin.", "x.com", "twitter.", "facebook.", "instagram.", "tiktok.",
})

# Sites with confirmed JA4T (transport-layer fingerprinting)
# These sites can detect bots even with perfect JA3 impersonation
JA4T_SITES = {
    "linkedin.": {"ja4t": True, "confidence": 0.95},
    "amazon.": {"ja4t": True, "confidence": 0.90},
    "google.": {"ja4t_suspected": True, "confidence": 0.70},
    "facebook.": {"ja4t": True, "confidence": 0.85},
    "booking.com": {"ja4t": True, "confidence": 0.90},
    "zillow.": {"ja4t": True, "confidence": 0.85},
    "walmart.": {"ja4t": True, "confidence": 0.85},
}

# Anti-bot detection patterns in headers
ANTIBOT_HEADERS = {
    "cf-ray": "cloudflare",
    "cf-cache-status": "cloudflare",
    "x-datadome": "datadome",
    "x-datadome-cid": "datadome",
    "x-akamai-transformed": "akamai",
    "akamai-grn": "akamai",
    "x-px-": "perimeterx",
}

# Anti-bot detection patterns in HTML
ANTIBOT_HTML_PATTERNS = {
    "cloudflare": [
        r"cf-browser-verification",
        r"cdn-cgi/challenge-platform",
        r"__cf_chl_",
        r"Cloudflare Ray ID",
        r"Just a moment\.\.\.",
    ],
    "cloudflare_uam": [
        r"Checking your browser before accessing",
        r"This process is automatic",
        r"Please Wait\.\.\. \| Cloudflare",
    ],
    "datadome": [
        r"datadome\.co",
        r"dd\.js",
        r"window\.ddjskey",
    ],
    "akamai": [
        r"_abck",
        r"bm_sz",
        r"ak_bmsc",
    ],
    "perimeterx": [
        r"_px3",
        r"_pxff_",
        r"px-captcha",
    ],
}


class ModeDetector:
    """Detect site characteristics and recommend scraping approach."""

    def __init__(self):
        pass

    async def detect(self, url: str, html: Optional[str] = None, headers: Optional[dict] = None) -> ScrapeProfile:
        """
        Detect site profile and recommend scraping approach.

        Args:
            url: Target URL
            html: Optional HTML content (for content-based detection)
            headers: Optional response headers (for header-based detection)

        Returns:
            ScrapeProfile with recommendations
        """
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Start with profile
        profile = ScrapeProfile(url=url, domain=domain)

        # Check known sites first
        for pattern, config in SITE_PROFILES.items():
            if pattern == "_default":
                continue
            if pattern in domain:
                profile.antibot = config.get("antibot")
                profile.recommended_tier = config.get("tier", 1)
                profile.needs_proxy = config.get("proxy", False)
                profile.needs_sticky = config.get("sticky", False)
                profile.antibot_confidence = 0.9
                profile.metadata["matched_pattern"] = pattern

                # Check for JA4T
                if config.get("ja4t"):
                    profile.uses_ja4t = True
                    profile.ja4t_confidence = 0.9
                elif config.get("ja4t_suspected"):
                    profile.uses_ja4t = True
                    profile.ja4t_confidence = 0.6
                break

        # Check if domain is sensitive (E9)
        for sensitive_pattern in SENSITIVE_DOMAINS:
            if sensitive_pattern in domain:
                profile.is_sensitive = True
                profile.recommended_tier = max(profile.recommended_tier, 2)
                profile.needs_proxy = True
                break

        # Also check JA4T_SITES for more specific detection
        for pattern, ja4t_config in JA4T_SITES.items():
            if pattern in domain:
                if ja4t_config.get("ja4t") or ja4t_config.get("ja4t_suspected"):
                    profile.uses_ja4t = True
                    profile.ja4t_confidence = max(
                        profile.ja4t_confidence,
                        ja4t_config.get("confidence", 0.7)
                    )
                break

        # If no known pattern, try detection
        if not profile.antibot:
            # Detect from headers
            if headers:
                for header, antibot in ANTIBOT_HEADERS.items():
                    if any(header.lower() in h.lower() for h in headers.keys()):
                        profile.antibot = antibot
                        profile.antibot_confidence = 0.7
                        profile.metadata["detected_via"] = "headers"
                        break

            # Detect from HTML
            if html and not profile.antibot:
                for antibot, patterns in ANTIBOT_HTML_PATTERNS.items():
                    for pattern in patterns:
                        if re.search(pattern, html, re.IGNORECASE):
                            profile.antibot = antibot
                            profile.antibot_confidence = 0.8
                            profile.metadata["detected_via"] = "html"
                            profile.metadata["detected_pattern"] = pattern
                            break
                    if profile.antibot:
                        break

        # Detect static data availability
        if html:
            profile.has_static_data = self._has_static_data(html)
            profile.detected_framework = self._detect_framework(html)

            # If has static data, might be able to use Tier 0
            if profile.has_static_data and not profile.antibot:
                profile.recommended_tier = 0

        # Determine recommended tier based on anti-bot
        if profile.antibot:
            if profile.antibot in ["akamai", "datadome", "perimeterx"]:
                profile.recommended_tier = 3
                profile.needs_proxy = True
            elif profile.antibot == "cloudflare_uam":
                profile.recommended_tier = 3
                profile.needs_proxy = True
            elif profile.antibot == "cloudflare":
                profile.recommended_tier = 2
                profile.needs_proxy = True
            else:
                profile.recommended_tier = 2

        # JA4T sites need at least tier 2 (browser) - HTTP tier won't work
        if profile.uses_ja4t and profile.ja4t_confidence > 0.5:
            profile.recommended_tier = max(profile.recommended_tier, 2)
            profile.needs_proxy = True
            profile.metadata["ja4t_skip_tier1"] = True

        # Apply default if still not set
        if not profile.antibot:
            default = SITE_PROFILES["_default"]
            profile.recommended_tier = default["tier"]
            profile.needs_proxy = default["proxy"]

        return profile

    def _has_static_data(self, html: str) -> bool:
        """Check if HTML contains extractable static data."""
        indicators = [
            "__NEXT_DATA__",
            "__NUXT__",
            "application/ld+json",
            "__APOLLO_STATE__",
            "__INITIAL_STATE__",
            "__PRELOADED_STATE__",
        ]
        return any(indicator in html for indicator in indicators)

    def _detect_framework(self, html: str) -> Optional[str]:
        """Detect frontend framework from HTML."""
        if "__NEXT_DATA__" in html:
            return "nextjs"
        if "__NUXT__" in html:
            return "nuxt"
        if "__remixContext" in html:
            return "remix"
        if "__GATSBY" in html:
            return "gatsby"
        if "ng-version" in html:
            return "angular"
        if 'data-reactroot' in html or 'data-react-' in html:
            return "react"
        if "Vue" in html and "__VUE__" in html:
            return "vue"
        return None

    async def probe(self, url: str, timeout: int = 10) -> ScrapeProfile:
        """
        Probe URL with HEAD request to detect anti-bot without fetching full content.

        Args:
            url: Target URL
            timeout: Request timeout

        Returns:
            ScrapeProfile with header-based detection
        """
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.head(url, timeout=timeout, follow_redirects=True)
                headers = dict(response.headers)

                # Also try GET if HEAD gives limited info
                if len(headers) < 5:
                    response = await client.get(url, timeout=timeout, follow_redirects=True)
                    headers = dict(response.headers)
                    html = response.text
                else:
                    html = None

                return await self.detect(url, html=html, headers=headers)

        except Exception as e:
            # Return basic profile on error
            profile = ScrapeProfile(url=url)
            profile.metadata["probe_error"] = str(e)
            return profile
