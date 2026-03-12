"""Tier 3: Full anti-detect browser via Camoufox."""

import asyncio
import base64
import os
from pathlib import Path
from typing import Optional
from tiers.base import BaseTier

# Unset DISPLAY to prevent X11 forwarding issues with headless Firefox in WSL
# This must be done before Camoufox tries to launch the browser
if os.environ.get("DISPLAY"):
    os.environ.pop("DISPLAY")
from core.result import ScrapeResult
from core.config import get_config
from extraction.static import StaticExtractor
from output.formatter import OutputFormatter
from proxy.manager import ProxyConfig, ProxyEmpireManager
from session.manager import SessionManager, SessionState
from behavior.human import HumanBehavior


class Tier3Camoufox(BaseTier):
    """
    Tier 3: Full anti-detect browser automation.

    Uses Camoufox, a Firefox fork with C++ level fingerprint spoofing.

    Features:
    - Protocol-level fingerprint spoofing (not JS injection)
    - BrowserForge fingerprint generation
    - GeoIP-based timezone/locale
    - Human-like cursor movement
    - Session persistence via storage_state
    - WebGL/Canvas/Audio fingerprint hiding
    """

    TIER_NUMBER = 3
    TIER_NAME = "camoufox"

    def __init__(self, behavior_intensity: float = 1.0, captcha_solver=None):
        self.proxy_manager = ProxyEmpireManager()
        self.session_manager = SessionManager()
        self.config = get_config()
        self.captcha_solver = captcha_solver
        # Loop detection (E6)
        from detection.loop_detector import ActionLoopDetector
        self._loop_detector = ActionLoopDetector()
        # Initialize behavior simulator with intensity from config or parameter
        intensity = behavior_intensity if behavior_intensity != 1.0 else self.config.behavior_intensity
        self.behavior = HumanBehavior(intensity=intensity)

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
        session_id: Optional[str] = None,
        humanize: float = 1.5,
        geoip: bool = True,
        headless: bool = True,
        wait_for: Optional[str] = None,
        actions: Optional[list] = None,
        screenshot: bool = False,
        screenshot_path: Optional[str] = None,
        full_page: bool = True,
        behavior_intensity: Optional[float] = None,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch URL with full anti-detect browser.

        Args:
            url: Target URL
            proxy: Optional proxy configuration (recommended for anti-detect)
            headers: Optional custom headers
            timeout: Page load timeout in seconds
            session_id: Session ID for persistence
            humanize: Human-like input delay (0 to disable, default 1.5s max)
            geoip: Auto-detect geolocation from proxy IP
            headless: Run headless (True) or with visible window (False)
            wait_for: CSS selector to wait for before extracting
            actions: List of page actions to perform
            screenshot: Capture screenshot and return as base64
            screenshot_path: Path to save screenshot (optional, uses temp if not provided)
            full_page: Capture full page screenshot (True) or viewport only (False)
            behavior_intensity: Behavioral simulation intensity (0.5-2.0)

        Returns:
            ScrapeResult with fetched content
        """
        # Reset per-scrape state (E6 fix: loop detector leaks across scrapes)
        self._loop_detector.reset()

        # Update behavior intensity if provided
        if behavior_intensity is not None:
            self.behavior = HumanBehavior(intensity=behavior_intensity)
        try:
            from camoufox import AsyncCamoufox

            # Build Camoufox options
            camoufox_opts = {
                "headless": headless,
                "humanize": humanize if humanize else None,
                "geoip": geoip,
            }

            # Configure proxy
            if proxy:
                camoufox_opts["proxy"] = {
                    "server": f"http://{proxy.host}:{proxy.port}",
                    "username": proxy.full_username,
                    "password": proxy.password,
                }

                # Use proxy geo for locale if geoip enabled
                if geoip:
                    camoufox_opts["locale"] = proxy.locale

            # Load session if exists
            session_state = None
            storage_state = None
            if session_id:
                session_state = self.session_manager.get(session_id)
                if session_state and session_state.storage_state_path:
                    storage_path = Path(session_state.storage_state_path)
                    if storage_path.exists():
                        storage_state = str(storage_path)

            async with AsyncCamoufox(**camoufox_opts) as browser:
                # Create context with storage state if available
                context_opts = {}
                if storage_state:
                    context_opts["storage_state"] = storage_state

                # GeoIP timezone from proxy (E4)
                if proxy and proxy.timezone:
                    context_opts["timezone_id"] = proxy.timezone

                context = await browser.new_context(**context_opts)

                # Tracker blocking (E8 — honor config)
                if self.config.block_trackers:
                    from detection import TRACKER_PATTERNS
                    for pattern in TRACKER_PATTERNS:
                        await context.route(pattern, lambda route: route.abort())

                # Shadow DOM piercing (E10)
                from extraction.shadow_dom import DEEP_QUERY_JS
                await context.add_init_script(DEEP_QUERY_JS)

                page = await context.new_page()

                # Set extra headers if provided
                if headers:
                    await page.set_extra_http_headers(headers)

                # Navigate with timeout
                try:
                    await page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
                except Exception as e:
                    if "timeout" in str(e).lower():
                        return ScrapeResult(
                            success=False,
                            tier_used=self.TIER_NUMBER,
                            url=url,
                            error=f"Page load timed out after {timeout}s",
                            error_type="Timeout",
                        )
                    raise

                # Wait for specific element
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=timeout * 1000)
                    except Exception:
                        pass  # Continue even if selector not found

                # Execute actions
                if actions:
                    await self._execute_actions(page, actions)

                # Small delay for dynamic content
                await asyncio.sleep(0.5)

                # Get content
                html = await page.content()
                final_url = page.url

                # Capture screenshot if requested
                screenshot_base64 = None
                actual_screenshot_path = None
                if screenshot or screenshot_path:
                    # Capture screenshot bytes
                    screenshot_bytes = await page.screenshot(full_page=full_page)
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

                    # Save to file if path provided
                    if screenshot_path:
                        actual_screenshot_path = screenshot_path
                        Path(screenshot_path).write_bytes(screenshot_bytes)

                # Get cookies for session
                cookies = await context.cookies()
                cookie_dict = {c["name"]: c["value"] for c in cookies}

                # Save session if ID provided
                if session_id:
                    # Save storage state
                    storage_path = self.session_manager.get_storage_state_path(session_id)
                    await context.storage_state(path=str(storage_path))

                    # Update session record
                    if not session_state:
                        session_state = self.session_manager.create(session_id, url)
                    session_state.cookies = cookie_dict
                    session_state.url = final_url
                    session_state.tier_used = self.TIER_NUMBER
                    session_state.storage_state_path = str(storage_path)
                    if proxy:
                        session_state.proxy_geo = proxy.geo
                        session_state.proxy_session_id = proxy.session_id
                    self.session_manager.save(session_state)

                # Check for blocks inside context for CAPTCHA solving (E1)
                if self._is_blocked(html):
                    solved = False
                    if self.captcha_solver and self.captcha_solver.configured:
                        solve_result = await self.captcha_solver.solve(page)
                        if solve_result.get("success"):
                            await asyncio.sleep(2)
                            html = await page.content()
                            solved = not self._is_blocked(html)
                    if not solved:
                        return ScrapeResult(
                            success=False,
                            tier_used=self.TIER_NUMBER,
                            url=url,
                            html=html,
                            error="Site blocked request (anti-detect failed)",
                            error_type="Blocked",
                            session_id=session_id,
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
                session_id=session_id,
                screenshot_base64=screenshot_base64,
                screenshot_path=actual_screenshot_path,
                metadata={
                    "humanize": humanize,
                    "geoip": geoip,
                    "proxy_geo": proxy.geo if proxy else None,
                    "session_restored": bool(storage_state),
                    "screenshot_captured": screenshot_base64 is not None,
                },
            )

        except ImportError as e:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=f"Camoufox not installed: {e}",
                error_type="ImportError",
            )
        except Exception as e:
            error_msg = str(e)

            # Classify error type
            error_type = type(e).__name__
            if "proxy" in error_msg.lower():
                error_type = "ProxyError"
            elif "timeout" in error_msg.lower():
                error_type = "Timeout"

            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=error_msg,
                error_type=error_type,
                session_id=session_id,
            )

    async def _execute_actions(self, page, actions: list) -> None:
        """Execute a list of page actions with human-like delays."""
        use_behavior = self.config.behavior_enabled

        for action in actions:
            action_type = action.get("type", action.get("action", ""))

            if action_type == "click":
                selector = action.get("selector") or action.get("ref")
                if use_behavior:
                    await self.behavior.move_to_element(page, selector, click=True)
                else:
                    await page.click(selector)
                await self.behavior.natural_wait(0.2, 0.4) if use_behavior else await asyncio.sleep(0.3)

            elif action_type == "fill":
                selector = action.get("selector") or action.get("ref")
                text = action.get("text", "")
                if use_behavior:
                    await self.behavior.human_type(page, selector, text)
                else:
                    await page.fill(selector, text)
                await asyncio.sleep(0.2)

            elif action_type == "type":
                selector = action.get("selector") or action.get("ref")
                text = action.get("text", "")
                if use_behavior:
                    await self.behavior.human_type(page, selector, text, clear_first=False)
                else:
                    await page.click(selector)
                    await page.type(selector, text, delay=50)
                await asyncio.sleep(0.2)

            elif action_type == "press":
                key = action.get("key", "Enter")
                await page.keyboard.press(key)
                await self.behavior.natural_wait(0.1, 0.3) if use_behavior else await asyncio.sleep(0.2)

            elif action_type == "wait":
                duration = action.get("duration", 1000)
                await asyncio.sleep(duration / 1000)

            elif action_type == "wait_for":
                selector = action.get("selector")
                timeout = action.get("timeout", 10000)
                await page.wait_for_selector(selector, timeout=timeout)

            elif action_type == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                if direction == "down":
                    await page.evaluate(f"window.scrollBy(0, {amount})")
                elif direction == "up":
                    await page.evaluate(f"window.scrollBy(0, -{amount})")
                # Natural pause after scroll to simulate reading
                if use_behavior:
                    await self.behavior.scroll_pause(amount)
                else:
                    await asyncio.sleep(0.3)

            elif action_type == "hover":
                selector = action.get("selector") or action.get("ref")
                if use_behavior:
                    await self.behavior.move_to_element(page, selector, click=False)
                else:
                    await page.hover(selector)
                await asyncio.sleep(0.2)

            elif action_type == "read":
                # New action: pause to simulate reading content
                if use_behavior:
                    content_length = action.get("content_length", 5000)
                    await self.behavior.reading_pause(content_length)

            # Loop detection after each action (E6)
            warning = self._loop_detector.record(action_type, action)
            if warning and "CRITICAL" in warning:
                break
            elif warning and "STUCK" in warning:
                from core.result import StuckDetected
                raise StuckDetected(warning)

    def _is_blocked(self, html: str) -> bool:
        """Check if response indicates a block (should be rare with Camoufox)."""
        indicators = [
            "Access Denied",
            "blocked by",
            "bot detected",
            "automated access",
            "unusual traffic",
        ]
        html_lower = html.lower()
        return any(indicator.lower() in html_lower for indicator in indicators)

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """
        Tier 3 can handle virtually all anti-bot systems.

        This is the highest-capability browser tier.
        """
        return True  # Camoufox can handle anything

    async def check_fingerprint(self) -> dict:
        """
        Test fingerprint consistency.

        Returns fingerprint check results from various detection sites.
        """
        try:
            from camoufox import AsyncCamoufox

            results = {}

            async with AsyncCamoufox(headless=True) as browser:
                page = await browser.new_page()

                # Check BrowserLeaks
                await page.goto("https://browserleaks.com/canvas", timeout=30000)
                await asyncio.sleep(2)
                results["browserleaks"] = await page.evaluate("""
                    () => ({
                        canvas: document.querySelector('.test-result')?.textContent || 'unknown',
                    })
                """)

                # Check Cloudflare
                await page.goto("https://nowsecure.nl", timeout=30000)
                await asyncio.sleep(3)
                results["nowsecure"] = {
                    "passed": "You are now accessing" in await page.content()
                }

            return results

        except Exception as e:
            return {"error": str(e)}
