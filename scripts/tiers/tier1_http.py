"""Tier 1: TLS-spoofed HTTP requests via Scrapling/curl_cffi."""

import asyncio
from typing import Optional, TYPE_CHECKING
from tiers.base import BaseTier, TierBlocked, TierTimeout
from core.result import ScrapeResult, Blocked, RateLimited, ProxyError
from extraction.static import StaticExtractor
from output.formatter import OutputFormatter
from proxy.manager import ProxyConfig, ProxyEmpireManager

if TYPE_CHECKING:
    from fingerprint.manager import FingerprintProfile


class Tier1HTTP(BaseTier):
    """
    Tier 1: TLS-spoofed HTTP requests.

    Uses Scrapling's AsyncFetcher which wraps curl_cffi with BrowserForge
    for automatic TLS fingerprint impersonation and realistic headers.

    Features:
    - JA3/JA4 fingerprint impersonation
    - HTTP/2 fingerprint matching
    - BrowserForge header generation
    - Automatic retry with backoff
    """

    TIER_NUMBER = 1
    TIER_NAME = "http"

    def __init__(self):
        self.proxy_manager = ProxyEmpireManager()

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
        impersonate: Optional[str] = None,
        fingerprint: Optional["FingerprintProfile"] = None,
        follow_redirects: bool = True,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch URL with TLS fingerprint spoofing.

        Args:
            url: Target URL
            proxy: Optional proxy configuration
            headers: Optional custom headers (merged with generated headers)
            timeout: Request timeout in seconds
            impersonate: Browser to impersonate (chrome143, firefox135, etc.)
            fingerprint: Optional FingerprintProfile for consistent identity
            follow_redirects: Whether to follow HTTP redirects

        Returns:
            ScrapeResult with fetched content
        """
        # Determine impersonation: fingerprint > explicit > proxy > default
        actual_impersonate = "chrome143"  # Default fallback
        if fingerprint:
            actual_impersonate = fingerprint.impersonate
        elif impersonate:
            actual_impersonate = impersonate
        elif proxy and proxy.browser:
            actual_impersonate = proxy.browser

        try:
            # Try Scrapling first (preferred)
            return await self._fetch_with_scrapling(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                impersonate=actual_impersonate,
                follow_redirects=follow_redirects,
                fingerprint=fingerprint,
            )
        except ImportError:
            # Fallback to direct curl_cffi
            return await self._fetch_with_curl_cffi(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=timeout,
                impersonate=actual_impersonate,
                follow_redirects=follow_redirects,
                fingerprint=fingerprint,
            )

    async def _fetch_with_scrapling(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        headers: Optional[dict],
        timeout: int,
        impersonate: str,
        follow_redirects: bool,
        fingerprint: Optional["FingerprintProfile"] = None,
    ) -> ScrapeResult:
        """Fetch using Scrapling's Fetcher (synchronous, run in executor)."""
        from scrapling import Fetcher

        try:
            # Configure Fetcher
            Fetcher.configure(auto_match=False)

            # Create fetcher
            fetcher = Fetcher()

            # Build proxy URL if configured
            proxy_url = proxy.curl_format if proxy else None

            # Merge headers: fingerprint > proxy-correlated > custom
            request_headers = {}
            if fingerprint:
                # Use fingerprint headers for consistency
                request_headers = {
                    "User-Agent": fingerprint.user_agent,
                    "Accept-Language": fingerprint.accept_language,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                }
            elif proxy:
                request_headers = self.proxy_manager.get_correlated_headers(proxy)
            if headers:
                request_headers.update(headers)

            # Run synchronous request in executor to not block event loop
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: fetcher.get(
                    url,
                    stealthy_headers=True,
                    follow_redirects=follow_redirects,
                    proxy=proxy_url,
                )
            )

            # Get HTML content first
            html = response.html_content if hasattr(response, 'html_content') else response.body

            # Check for soft blocks (Cloudflare challenge page, etc.)
            if self._is_challenge_page(html):
                return self._create_blocked_result(url, response.status, "Challenge page detected")

            # Check for blocks - but only if no meaningful content
            # A 403 with actual content (test page) is a successful fetch
            if response.status == 403:
                if not html or len(html.strip()) < 200 or self._is_block_page(html):
                    return self._create_blocked_result(url, response.status, "403 Forbidden")
                # Has content - return as success with 403 status
            if response.status == 429:
                return self._create_rate_limited_result(url, response.status)

            # Extract static data if available
            static_data = None
            if StaticExtractor.has_static_data(html):
                static_data = StaticExtractor.extract_all(html)

            # Convert to markdown
            markdown = OutputFormatter.html_to_markdown(html)

            return ScrapeResult(
                success=True,
                tier_used=self.TIER_NUMBER,
                status_code=response.status,
                url=url,
                final_url=str(response.url) if hasattr(response, 'url') else url,
                html=html,
                markdown=markdown,
                static_data=static_data,
                cookies=dict(response.cookies) if hasattr(response, 'cookies') else {},
                metadata={
                    "impersonate": impersonate,
                    "proxy_geo": proxy.geo if proxy else None,
                    "content_length": len(html),
                    "fingerprint_id": fingerprint.fingerprint_id if fingerprint else None,
                },
            )

        except asyncio.TimeoutError:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=f"Request timed out after {timeout}s",
                error_type="Timeout",
            )
        except Exception as e:
            error_msg = str(e)
            if "proxy" in error_msg.lower():
                return ScrapeResult(
                    success=False,
                    tier_used=self.TIER_NUMBER,
                    url=url,
                    error=error_msg,
                    error_type="ProxyError",
                )
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=error_msg,
                error_type=type(e).__name__,
            )

    async def _fetch_with_curl_cffi(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        headers: Optional[dict],
        timeout: int,
        impersonate: str,
        follow_redirects: bool,
        fingerprint: Optional["FingerprintProfile"] = None,
    ) -> ScrapeResult:
        """Fallback: Direct curl_cffi usage."""
        from curl_cffi import requests as curl_requests

        try:
            # Build headers: fingerprint > proxy-correlated > custom
            request_headers = {}
            if fingerprint:
                request_headers = {
                    "User-Agent": fingerprint.user_agent,
                    "Accept-Language": fingerprint.accept_language,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                }
            elif proxy:
                request_headers = self.proxy_manager.get_correlated_headers(proxy)
            if headers:
                request_headers.update(headers)

            # Build proxy dict
            proxies = proxy.dict_format if proxy else None

            # Make request
            response = curl_requests.get(
                url,
                impersonate=impersonate,
                headers=request_headers if request_headers else None,
                proxies=proxies,
                timeout=timeout,
                allow_redirects=follow_redirects,
            )

            html = response.text

            # Check for soft blocks
            if self._is_challenge_page(html):
                return self._create_blocked_result(url, response.status_code, "Challenge page detected")

            # Check for blocks - but only if no meaningful content
            if response.status_code == 403:
                if not html or len(html.strip()) < 200 or self._is_block_page(html):
                    return self._create_blocked_result(url, response.status_code, "403 Forbidden")
            if response.status_code == 429:
                return self._create_rate_limited_result(url, response.status_code)

            # Extract static data
            static_data = None
            if StaticExtractor.has_static_data(html):
                static_data = StaticExtractor.extract_all(html)

            # Convert to markdown
            markdown = OutputFormatter.html_to_markdown(html)

            return ScrapeResult(
                success=True,
                tier_used=self.TIER_NUMBER,
                status_code=response.status_code,
                url=url,
                final_url=str(response.url),
                html=html,
                markdown=markdown,
                static_data=static_data,
                cookies=dict(response.cookies),
                metadata={
                    "impersonate": impersonate,
                    "proxy_geo": proxy.geo if proxy else None,
                    "fingerprint_id": fingerprint.fingerprint_id if fingerprint else None,
                },
            )

        except Exception as e:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=str(e),
                error_type=type(e).__name__,
            )

    def _is_challenge_page(self, html: str) -> bool:
        """Check if response is a challenge/block page."""
        indicators = [
            "Just a moment...",  # Cloudflare
            "Please Wait... | Cloudflare",
            "Checking your browser",
            "Attention Required! | Cloudflare",
            "cf-browser-verification",
            "challenge-platform",
            "_cf_chl",
            "datadome",
        ]
        html_lower = html.lower()
        return any(indicator.lower() in html_lower for indicator in indicators)

    def _is_block_page(self, html: str) -> bool:
        """
        Check if 403 response is an actual block vs test/informational page.

        Returns True if it looks like a real anti-bot block.
        Returns False if it has meaningful content (test page, API error, etc.)
        """
        html_lower = html.lower()

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
        ]

        # If it has block indicators and is short, it's likely a real block
        if any(ind in html_lower for ind in block_indicators):
            # But check if it's a test page explaining the 403
            test_indicators = ["test", "example", "scraper", "crawl", "status code"]
            if any(ind in html_lower for ind in test_indicators):
                return False  # Test page, not a real block
            return True

        return False

    def _create_blocked_result(self, url: str, status: int, reason: str) -> ScrapeResult:
        """Create a blocked result."""
        return ScrapeResult(
            success=False,
            tier_used=self.TIER_NUMBER,
            status_code=status,
            url=url,
            error=reason,
            error_type="Blocked",
        )

    def _create_rate_limited_result(self, url: str, status: int) -> ScrapeResult:
        """Create a rate limited result."""
        return ScrapeResult(
            success=False,
            tier_used=self.TIER_NUMBER,
            status_code=status,
            url=url,
            error="Rate limited (429)",
            error_type="RateLimited",
        )

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """
        Tier 1 can handle most sites without heavy anti-bot.

        Returns False for known sites requiring browser execution:
        - Sites with Cloudflare Under Attack Mode
        - Sites requiring JavaScript rendering
        """
        if profile:
            # Can't handle Cloudflare UAM or heavy anti-bot
            if profile.antibot in ["cloudflare_uam", "datadome", "akamai"]:
                return False
            # Can't handle JS-required sites
            if profile.requires_js:
                return False
        return True
