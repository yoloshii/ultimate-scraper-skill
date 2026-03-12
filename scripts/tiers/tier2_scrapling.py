"""Tier 2: Stealth browser via Scrapling StealthyFetcher (Patchright)."""

import asyncio
from typing import Optional
from tiers.base import BaseTier
from core.result import ScrapeResult
from extraction.static import StaticExtractor
from output.formatter import OutputFormatter
from proxy.manager import ProxyConfig, ProxyEmpireManager
from core.config import get_config


# Challenge pages that Tier 2 cannot solve - fail fast instead of hanging
UNSOLVABLE_CHALLENGE_INDICATORS = [
    "just a moment...",
    "checking your browser",
    "cf-browser-verification",
    "challenge-platform",
    "_cf_chl",
    "please wait while we verify",
    "ddos protection by",
]


# CloakBrowser availability cache (E2)
_cloakbrowser_available = None


async def _check_cloakbrowser() -> bool:
    """Check if CloakBrowser is available and enabled."""
    global _cloakbrowser_available
    if _cloakbrowser_available is not None:
        return _cloakbrowser_available

    config = get_config()
    # "0" = disabled, "1" = forced, "auto" = detect
    if config.cloakbrowser_enabled == "0":
        _cloakbrowser_available = False
        return False

    try:
        from cloakbrowser import ensure_binary
        _cloakbrowser_available = True
    except ImportError:
        _cloakbrowser_available = False
        # If forced ("1") but not installed, remain False — caller gets Patchright fallback
        if config.cloakbrowser_enabled == "1":
            import sys
            print("[CloakBrowser] Forced but not installed — falling back to Patchright", file=sys.stderr)

    return _cloakbrowser_available


class Tier2Scrapling(BaseTier):
    """
    Tier 2: Stealth browser automation.

    Uses Scrapling's StealthyFetcher which wraps Patchright (patched Playwright)
    with additional stealth features.

    Features:
    - Cloudflare bypass (solve_cloudflare=True)
    - Canvas fingerprint hiding
    - WebRTC blocking
    - Page actions support
    - JavaScript execution

    Timeout Strategy:
    - Hard timeout wrapper prevents infinite hangs on challenge pages
    - Early challenge detection fails fast to escalate to Tier 3
    """

    TIER_NUMBER = 2
    TIER_NAME = "scrapling"

    # Tier 2 should fail fast on challenges it can't solve
    CHALLENGE_TIMEOUT = 15  # Seconds to wait before declaring challenge unsolvable

    def __init__(self, captcha_solver=None):
        self.proxy_manager = ProxyEmpireManager()
        self.captcha_solver = captcha_solver

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
        solve_cloudflare: bool = True,
        block_webrtc: bool = True,
        wait_for: Optional[str] = None,
        actions: Optional[list] = None,
        screenshot: bool = False,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch URL with stealth browser.

        Args:
            url: Target URL
            proxy: Optional proxy configuration
            headers: Optional custom headers
            timeout: Page load timeout in seconds
            solve_cloudflare: Attempt to bypass Cloudflare challenges
            block_webrtc: Block WebRTC to prevent IP leak
            wait_for: CSS selector to wait for before extracting
            actions: List of page actions to perform
            screenshot: Whether to capture screenshot

        Returns:
            ScrapeResult with fetched content
        """
        # Use shorter timeout for challenge detection
        effective_timeout = min(timeout, self.CHALLENGE_TIMEOUT)

        # Try CloakBrowser first (C++ level patches), fallback to Patchright (E2)
        if await _check_cloakbrowser():
            return await self._fetch_with_cloakbrowser(
                url=url,
                proxy=proxy,
                headers=headers,
                timeout=effective_timeout,
                wait_for=wait_for,
                actions=actions,
            )

        return await self._fetch_with_patchright(
            url=url,
            proxy=proxy,
            headers=headers,
            timeout=effective_timeout,
            wait_for=wait_for,
            actions=actions,
        )

    def _is_unsolvable_challenge(self, html: str) -> bool:
        """Check if page contains a challenge that Tier 2 cannot solve."""
        html_lower = html.lower()
        return any(indicator in html_lower for indicator in UNSOLVABLE_CHALLENGE_INDICATORS)

    async def _fetch_with_patchright(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        headers: Optional[dict],
        timeout: int,
        wait_for: Optional[str],
        actions: Optional[list],
    ) -> ScrapeResult:
        """Fallback to direct Patchright usage with hard timeout."""
        try:
            from patchright.async_api import async_playwright
        except ImportError:
            from playwright.async_api import async_playwright

        browser = None
        try:
            # Wrap entire browser operation in hard timeout
            async def _browser_fetch():
                nonlocal browser
                async with async_playwright() as p:
                    # Build launch options
                    launch_opts = {
                        "headless": True,
                    }

                    # Build context options
                    context_opts = {}
                    if proxy:
                        context_opts["proxy"] = {
                            "server": f"http://{proxy.host}:{proxy.port}",
                            "username": proxy.full_username,
                            "password": proxy.password,
                        }
                    if headers:
                        context_opts["extra_http_headers"] = headers

                    # GeoIP timezone/locale from proxy (E4)
                    if proxy and proxy.timezone:
                        context_opts["timezone_id"] = proxy.timezone
                    if proxy and proxy.locale:
                        context_opts["locale"] = proxy.locale

                    # Launch browser
                    browser = await p.chromium.launch(**launch_opts)
                    context = await browser.new_context(**context_opts)

                    # Tracker blocking (E8 — honor config)
                    config = get_config()
                    if config.block_trackers:
                        from detection import TRACKER_PATTERNS
                        for pattern in TRACKER_PATTERNS:
                            await context.route(pattern, lambda route: route.abort())

                    # Shadow DOM piercing (E10)
                    from extraction.shadow_dom import DEEP_QUERY_JS
                    await context.add_init_script(DEEP_QUERY_JS)

                    page = await context.new_page()

                    # Navigate with reduced timeout
                    await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

                    # Quick challenge check before waiting
                    html = await page.content()
                    if self._is_unsolvable_challenge(html):
                        # Attempt CAPTCHA solving if configured (E1)
                        solved = False
                        if self.captcha_solver and self.captcha_solver.configured:
                            solve_result = await self.captcha_solver.solve(page)
                            if solve_result.get("success"):
                                await asyncio.sleep(2)
                                html = await page.content()
                                solved = not self._is_unsolvable_challenge(html)
                        if not solved:
                            await browser.close()
                            return ScrapeResult(
                                success=False,
                                tier_used=self.TIER_NUMBER,
                                url=url,
                                html=html,
                                error="Challenge page detected (requires Tier 3)",
                                error_type="ChallengeDetected",
                            )

                    # Wait for specific element (with shadow DOM fallback - E10)
                    if wait_for:
                        try:
                            await page.wait_for_selector(wait_for, timeout=timeout * 1000)
                        except Exception:
                            pass  # May be in shadow DOM, continue

                    # Execute actions
                    if actions:
                        await self._execute_actions(page, actions)

                    # Get final content
                    html = await page.content()
                    final_url = page.url

                    # Get cookies
                    cookies = await context.cookies()
                    cookie_dict = {c["name"]: c["value"] for c in cookies}

                    await browser.close()

                    # Check for blocks
                    if self._is_blocked(html, 200):
                        return ScrapeResult(
                            success=False,
                            tier_used=self.TIER_NUMBER,
                            url=url,
                            html=html,
                            error="Site blocked request",
                            error_type="Blocked",
                        )

                    # Extract static data
                    static_data = None
                    if StaticExtractor.has_static_data(html):
                        static_data = StaticExtractor.extract_all(html)

                    # Convert to markdown
                    markdown = OutputFormatter.html_to_markdown(html)

                    return ScrapeResult(
                        success=True,
                        tier_used=self.TIER_NUMBER,
                        status_code=200,
                        url=url,
                        final_url=final_url,
                        html=html,
                        markdown=markdown,
                        static_data=static_data,
                        cookies=cookie_dict,
                        metadata={
                            "method": "patchright",
                            "proxy_geo": proxy.geo if proxy else None,
                        },
                    )

            # Hard timeout wrapper
            return await asyncio.wait_for(_browser_fetch(), timeout=timeout + 10)

        except asyncio.TimeoutError:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=f"Patchright timed out after {timeout}s (likely unsolvable challenge)",
                error_type="ChallengeTimeout",
            )
        except Exception as e:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _fetch_with_cloakbrowser(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        headers: Optional[dict],
        timeout: int,
        wait_for: Optional[str],
        actions: Optional[list],
    ) -> ScrapeResult:
        """Fetch using CloakBrowser (C++ patched Chromium) for maximum stealth (E2)."""
        try:
            from cloakbrowser import ensure_binary
            from cloakbrowser.config import get_default_stealth_args
        except ImportError:
            return await self._fetch_with_patchright(url, proxy, headers, timeout, wait_for, actions)

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            from patchright.async_api import async_playwright

        browser = None
        try:
            async def _browser_fetch():
                nonlocal browser
                try:
                    binary_path = ensure_binary()
                except Exception:
                    # ensure_binary() failed (download error, unsupported platform, etc.)
                    # Graceful fallback to Patchright instead of generic error (E2 fix)
                    return await self._fetch_with_patchright(url, proxy, headers, timeout, wait_for, actions)

                cloak_args = get_default_stealth_args()

                # Add WebMCP Chrome flag if enabled (E5)
                config = get_config()
                if config.webmcp_enabled != "0":
                    cloak_args = list(cloak_args) + ["--enable-features=WebMCPTesting"]

                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        executable_path=binary_path,
                        args=cloak_args,
                        headless=True,
                    )

                    context_opts = {
                        "viewport": {"width": 1920, "height": 947},
                    }
                    if proxy:
                        context_opts["proxy"] = {
                            "server": f"http://{proxy.host}:{proxy.port}",
                            "username": proxy.full_username,
                            "password": proxy.password,
                        }
                    if headers:
                        context_opts["extra_http_headers"] = headers

                    # GeoIP timezone/locale (E4)
                    if proxy and proxy.timezone:
                        context_opts["timezone_id"] = proxy.timezone
                    if proxy and proxy.locale:
                        context_opts["locale"] = proxy.locale

                    context = await browser.new_context(**context_opts)

                    # Tracker blocking (E8 — honor config)
                    if config.block_trackers:
                        from detection import TRACKER_PATTERNS
                        for pattern in TRACKER_PATTERNS:
                            await context.route(pattern, lambda route: route.abort())

                    # Shadow DOM piercing (E10)
                    from extraction.shadow_dom import DEEP_QUERY_JS
                    await context.add_init_script(DEEP_QUERY_JS)

                    # WebMCP injection — CloakBrowser path only (E5)
                    if config.webmcp_enabled != "0":
                        from extraction.webmcp import inject_webmcp
                        await inject_webmcp(context)

                    page = await context.new_page()
                    await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

                    # Challenge check with CAPTCHA solving (E1)
                    html = await page.content()
                    if self._is_unsolvable_challenge(html):
                        solved = False
                        if self.captcha_solver and self.captcha_solver.configured:
                            solve_result = await self.captcha_solver.solve(page)
                            if solve_result.get("success"):
                                await asyncio.sleep(2)
                                html = await page.content()
                                solved = not self._is_unsolvable_challenge(html)
                        if not solved:
                            await browser.close()
                            return ScrapeResult(
                                success=False, tier_used=self.TIER_NUMBER, url=url,
                                html=html, error="Challenge detected (CloakBrowser)",
                                error_type="ChallengeDetected",
                            )

                    # Wait for element (E10 shadow DOM fallback)
                    if wait_for:
                        try:
                            await page.wait_for_selector(wait_for, timeout=timeout * 1000)
                        except Exception:
                            pass

                    if actions:
                        await self._execute_actions(page, actions)

                    # WebMCP tool discovery after page load (E5)
                    webmcp_tools = None
                    if config.webmcp_enabled != "0":
                        try:
                            from extraction.webmcp import discover_tools
                            webmcp_result = await discover_tools(page)
                            if webmcp_result.get("available") and webmcp_result.get("tools"):
                                webmcp_tools = webmcp_result["tools"]
                        except Exception:
                            pass

                    html = await page.content()
                    final_url = page.url
                    cookies = await context.cookies()
                    cookie_dict = {c["name"]: c["value"] for c in cookies}
                    await browser.close()

                    if self._is_blocked(html, 200):
                        return ScrapeResult(
                            success=False, tier_used=self.TIER_NUMBER, url=url,
                            html=html, error="Site blocked request",
                            error_type="Blocked",
                        )

                    static_data = None
                    if StaticExtractor.has_static_data(html):
                        static_data = StaticExtractor.extract_all(html)

                    markdown = OutputFormatter.html_to_markdown(html)

                    metadata = {
                        "method": "cloakbrowser",
                        "proxy_geo": proxy.geo if proxy else None,
                    }
                    if webmcp_tools:
                        metadata["webmcp_tools"] = list(webmcp_tools.keys())

                    return ScrapeResult(
                        success=True, tier_used=self.TIER_NUMBER, status_code=200,
                        url=url, final_url=final_url, html=html, markdown=markdown,
                        static_data=static_data, cookies=cookie_dict,
                        metadata=metadata,
                    )

            return await asyncio.wait_for(_browser_fetch(), timeout=timeout + 10)

        except asyncio.TimeoutError:
            return ScrapeResult(
                success=False, tier_used=self.TIER_NUMBER, url=url,
                error=f"CloakBrowser timed out after {timeout}s",
                error_type="ChallengeTimeout",
            )
        except Exception as e:
            return ScrapeResult(
                success=False, tier_used=self.TIER_NUMBER, url=url,
                error=str(e), error_type=type(e).__name__,
            )

    async def _execute_actions(self, page, actions: list) -> None:
        """Execute a list of page actions."""
        for action in actions:
            action_type = action.get("type", action.get("action", ""))

            if action_type == "click":
                selector = action.get("selector") or action.get("ref")
                await page.click(selector)

            elif action_type == "fill":
                selector = action.get("selector") or action.get("ref")
                text = action.get("text", "")
                await page.fill(selector, text)

            elif action_type == "type":
                selector = action.get("selector") or action.get("ref")
                text = action.get("text", "")
                await page.type(selector, text)

            elif action_type == "press":
                key = action.get("key", "Enter")
                await page.keyboard.press(key)

            elif action_type == "wait":
                duration = action.get("duration", 1000)
                await asyncio.sleep(duration / 1000)

            elif action_type == "wait_for":
                selector = action.get("selector")
                await page.wait_for_selector(selector)

            elif action_type == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                if direction == "down":
                    await page.evaluate(f"window.scrollBy(0, {amount})")
                elif direction == "up":
                    await page.evaluate(f"window.scrollBy(0, -{amount})")

    def _is_blocked(self, html: str, status: int) -> bool:
        """Check if response indicates a block."""
        if status in [403, 429, 503]:
            return True

        indicators = [
            "Access Denied",
            "blocked by",
            "bot detected",
            "Please enable JavaScript",
            "Checking your browser",
            "Just a moment...",
            "cf-browser-verification",
        ]
        html_lower = html.lower()
        return any(indicator.lower() in html_lower for indicator in indicators)

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """
        Tier 2 can handle sites with basic anti-bot.

        Returns False for sites requiring full anti-detect browser.
        """
        if profile:
            # Can handle Cloudflare but not DataDome/Akamai
            if profile.antibot in ["datadome", "akamai", "perimeterx"]:
                return False
        return True
