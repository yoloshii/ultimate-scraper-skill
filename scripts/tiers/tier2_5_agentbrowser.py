"""Tier 2.5: Agent-browser stealth automation with network interception."""

import asyncio
import base64
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional
from tiers.base import BaseTier
from core.result import ScrapeResult
from extraction.static import StaticExtractor
from output.formatter import OutputFormatter
from proxy.manager import ProxyConfig


# Shared tracker patterns from detection module (E8)
from detection import TRACKER_PATTERNS as BLOCKED_PATTERNS


class Tier2_5AgentBrowser(BaseTier):
    """
    Tier 2.5: Agent-browser automation.

    Lighter than Camoufox (no 713MB download), provides:
    - Chromium-based stealth browser
    - Network interception (block trackers/fingerprinters)
    - Session state persistence
    - Full page interaction capabilities

    Use when Scrapling fails but before escalating to Camoufox.
    """

    TIER_NUMBER = 2.5
    TIER_NAME = "agent-browser"

    def __init__(self):
        self._session_name = None
        self._routes_set = False
        # Loop detection (E6)
        from detection.loop_detector import ActionLoopDetector
        self._loop_detector = ActionLoopDetector()

    def _run_cmd(self, *args, capture_output=True, timeout=60) -> subprocess.CompletedProcess:
        """Run agent-browser command."""
        cmd = ["agent-browser"] + list(args)
        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
        )

    def _run_cmd_with_session(self, *args, **kwargs) -> subprocess.CompletedProcess:
        """Run command with session flag if set."""
        if self._session_name:
            return self._run_cmd("--session", self._session_name, *args, **kwargs)
        return self._run_cmd(*args, **kwargs)

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
        wait_for: Optional[str] = None,
        actions: Optional[list] = None,
        session_id: Optional[str] = None,
        block_trackers: bool = True,
        screenshot: bool = False,
        full_page: bool = True,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch URL with agent-browser.

        Args:
            url: Target URL
            proxy: Optional proxy configuration
            headers: Optional custom headers
            timeout: Page load timeout in seconds
            wait_for: CSS selector to wait for
            actions: List of browser actions
            session_id: Named session for isolation
            block_trackers: Block tracking/fingerprinting scripts
            screenshot: Capture screenshot and return as base64
            full_page: Capture full page screenshot (True) or viewport only (False)

        Returns:
            ScrapeResult with fetched content
        """
        self._session_name = session_id or f"scraper_{hash(url) % 10000:04d}"

        # Reset per-scrape state (E6 fix: loop detector leaks across scrapes)
        self._loop_detector.reset()
        self._routes_set = False

        try:
            # Build open command with options
            open_args = ["open", url]

            # Add proxy if configured
            if proxy:
                proxy_url = proxy.curl_format
                open_args.extend(["--proxy", proxy_url])

            # Add headers if provided
            if headers:
                open_args.extend(["--headers", json.dumps(headers)])

            # Run in executor to not block
            loop = asyncio.get_event_loop()

            # Open page
            result = await loop.run_in_executor(
                None,
                lambda: self._run_cmd_with_session(*open_args, timeout=timeout + 10)
            )

            if result.returncode != 0:
                return ScrapeResult(
                    success=False,
                    tier_used=self.TIER_NUMBER,
                    url=url,
                    error=f"Failed to open URL: {result.stderr}",
                    error_type="NavigationError",
                )

            # Set up network interception for trackers (E8: honor config)
            if block_trackers:
                for pattern in BLOCKED_PATTERNS:
                    await loop.run_in_executor(
                        None,
                        lambda p=pattern: self._run_cmd_with_session(
                            "network", "route", p, "--abort"
                        )
                    )
            # Inject Shadow DOM piercing BEFORE wait (E10 fix: inject early so deepQuery is available)
            from extraction.shadow_dom import DEEP_QUERY_JS
            await loop.run_in_executor(
                None,
                lambda: self._run_cmd_with_session("eval", DEEP_QUERY_JS)
            )

            # Wait for specific element if requested
            if wait_for:
                await loop.run_in_executor(
                    None,
                    lambda: self._run_cmd_with_session(
                        "wait", wait_for, timeout=timeout * 1000
                    )
                )
            else:
                # Default: wait for network idle
                await loop.run_in_executor(
                    None,
                    lambda: self._run_cmd_with_session("wait", "--load", "networkidle")
                )

            # Execute actions if provided
            if actions:
                await self._execute_actions(actions)

            # Get page content
            # First get snapshot to check for interactive elements
            snapshot_result = await loop.run_in_executor(
                None,
                lambda: self._run_cmd_with_session("snapshot", "-i", "-c", "--json")
            )

            # Get full HTML via eval
            html_result = await loop.run_in_executor(
                None,
                lambda: self._run_cmd_with_session(
                    "eval", "document.documentElement.outerHTML"
                )
            )

            if html_result.returncode != 0:
                return ScrapeResult(
                    success=False,
                    tier_used=self.TIER_NUMBER,
                    url=url,
                    error=f"Failed to get content: {html_result.stderr}",
                    error_type="ContentError",
                )

            html = html_result.stdout.strip()

            # Handle JSON wrapper if present
            if html.startswith('{') or html.startswith('"'):
                try:
                    html = json.loads(html)
                    if isinstance(html, dict):
                        html = html.get("result", html.get("value", str(html)))
                except json.JSONDecodeError:
                    pass

            # Get final URL
            url_result = await loop.run_in_executor(
                None,
                lambda: self._run_cmd_with_session("get", "url")
            )
            final_url = url_result.stdout.strip() if url_result.returncode == 0 else url

            # Get cookies
            cookies_result = await loop.run_in_executor(
                None,
                lambda: self._run_cmd_with_session("cookies", "--json")
            )
            cookies = {}
            if cookies_result.returncode == 0:
                try:
                    cookie_data = json.loads(cookies_result.stdout)
                    if isinstance(cookie_data, list):
                        cookies = {c["name"]: c["value"] for c in cookie_data if "name" in c}
                except (json.JSONDecodeError, KeyError):
                    pass

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

            # Capture screenshot if requested
            screenshot_path = None
            screenshot_base64 = None
            if screenshot:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                    screenshot_path = f.name

                # Build screenshot command with full_page option
                screenshot_args = [screenshot_path]
                if full_page:
                    screenshot_args.append("--full")

                await loop.run_in_executor(
                    None,
                    lambda: self._run_cmd_with_session("screenshot", *screenshot_args)
                )

                # Read and encode to base64
                if Path(screenshot_path).exists():
                    screenshot_bytes = Path(screenshot_path).read_bytes()
                    screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')

            # Close session on success to prevent leaks
            try:
                await loop.run_in_executor(
                    None,
                    lambda: self._run_cmd_with_session("close")
                )
            except Exception:
                pass

            return ScrapeResult(
                success=True,
                tier_used=self.TIER_NUMBER,
                status_code=200,
                url=url,
                final_url=final_url,
                html=html,
                markdown=markdown,
                static_data=static_data,
                cookies=cookies,
                screenshot_base64=screenshot_base64,
                screenshot_path=screenshot_path,
                metadata={
                    "method": "agent-browser",
                    "session": self._session_name,
                    "trackers_blocked": block_trackers,
                    "proxy_geo": proxy.geo if proxy else None,
                    "screenshot_captured": screenshot_base64 is not None,
                    "snapshot": snapshot_result.stdout if snapshot_result.returncode == 0 else None,
                },
            )

        except subprocess.TimeoutExpired:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=f"Page load timed out after {timeout}s",
                error_type="Timeout",
            )
        except FileNotFoundError:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error="agent-browser not installed. Run: npm install -g agent-browser",
                error_type="DependencyError",
            )
        except Exception as e:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _execute_actions(self, actions: list) -> None:
        """Execute browser actions via agent-browser CLI."""
        loop = asyncio.get_event_loop()

        for action in actions:
            action_type = action.get("type", action.get("action", ""))

            if action_type == "click":
                ref = action.get("ref") or action.get("selector")
                await loop.run_in_executor(
                    None,
                    lambda r=ref: self._run_cmd_with_session("click", r)
                )

            elif action_type == "fill":
                ref = action.get("ref") or action.get("selector")
                text = action.get("text", "")
                await loop.run_in_executor(
                    None,
                    lambda r=ref, t=text: self._run_cmd_with_session("fill", r, t)
                )

            elif action_type == "type":
                ref = action.get("ref") or action.get("selector")
                text = action.get("text", "")
                await loop.run_in_executor(
                    None,
                    lambda r=ref, t=text: self._run_cmd_with_session("type", r, t)
                )

            elif action_type == "press":
                key = action.get("key", "Enter")
                await loop.run_in_executor(
                    None,
                    lambda k=key: self._run_cmd_with_session("press", k)
                )

            elif action_type == "wait":
                duration = action.get("duration", 1000)
                await loop.run_in_executor(
                    None,
                    lambda d=duration: self._run_cmd_with_session("wait", str(d))
                )

            elif action_type == "wait_for":
                selector = action.get("selector")
                await loop.run_in_executor(
                    None,
                    lambda s=selector: self._run_cmd_with_session("wait", s)
                )

            elif action_type == "scroll":
                direction = action.get("direction", "down")
                amount = action.get("amount", 500)
                await loop.run_in_executor(
                    None,
                    lambda d=direction, a=amount: self._run_cmd_with_session(
                        "scroll", d, str(a)
                    )
                )

            elif action_type == "snapshot":
                # Re-snapshot to get updated refs
                await loop.run_in_executor(
                    None,
                    lambda: self._run_cmd_with_session("snapshot", "-i")
                )

            # Loop detection after each action (E6)
            warning = self._loop_detector.record(action_type, action)
            if warning and "CRITICAL" in warning:
                break
            elif warning and "STUCK" in warning:
                from core.result import StuckDetected
                raise StuckDetected(warning)

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
            "challenge-platform",
        ]
        html_lower = html.lower()
        return any(indicator.lower() in html_lower for indicator in indicators)

    async def close(self):
        """Close browser session."""
        if self._session_name:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: self._run_cmd_with_session("close")
                )
            except (FileNotFoundError, OSError):
                # agent-browser not installed or not in PATH - silently ignore
                pass
            finally:
                self._session_name = None
                self._routes_set = False

    def can_handle(self, url: str, profile=None) -> bool:
        """
        Tier 2.5 can handle most sites with basic-to-moderate anti-bot.

        Better than Scrapling for sites needing network interception.
        Falls back to Camoufox for aggressive anti-detect requirements.
        """
        if profile:
            # Can't handle aggressive anti-detect (need Camoufox)
            if profile.antibot in ["datadome", "akamai", "perimeterx"]:
                return False
        return True
