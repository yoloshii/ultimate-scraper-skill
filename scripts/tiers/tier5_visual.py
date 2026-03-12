"""Tier 5: Visual LLM extraction from screenshots.

Uses Tier 2.5 or Tier 3 to capture screenshots, then routes to
vision-capable LLMs for extraction. Bypasses DOM-based detection
since extraction happens on the image, not the page content.
"""

import base64
from typing import Optional, Literal
from pathlib import Path

from tiers.base import BaseTier
from core.result import ScrapeResult
from proxy.manager import ProxyConfig
from extraction.vision_router import VisionExtractionRouter


class Tier5Visual(BaseTier):
    """
    Tier 5: Visual extraction using screenshots + Vision LLM.

    This tier captures a full-page screenshot using browser tiers
    (2.5 or 3) and extracts data using vision-capable LLMs.

    Benefits:
    - Bypasses DOM monitoring/mutation detection
    - Works on heavily obfuscated pages
    - Extracts from canvas-rendered content
    - Handles dynamic/JS-heavy pages

    Limitations:
    - Slower than text-based extraction
    - May miss content below fold (unless full_page=True)
    - Requires vision-capable LLM
    """

    TIER_NUMBER = 5
    TIER_NAME = "visual"

    def __init__(self):
        self.vision_router = VisionExtractionRouter()
        self._browser_tier = None

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        extract_prompt: str = "",
        extract_schema: Optional[dict] = None,
        screenshot_source: Literal["tier2.5", "tier3"] = "tier3",
        full_page: bool = True,
        headers: Optional[dict] = None,
        timeout: int = 60,
        wait_for: Optional[str] = None,
        session_id: Optional[str] = None,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch URL, capture screenshot, and extract with vision LLM.

        Args:
            url: Target URL
            proxy: Optional proxy configuration
            extract_prompt: Natural language description of what to extract
            extract_schema: Optional JSON schema for structured output
            screenshot_source: Which tier to use for screenshot ("tier2.5" or "tier3")
            full_page: Capture full page screenshot (vs viewport only)
            headers: Optional custom headers
            timeout: Request timeout in seconds
            wait_for: CSS selector to wait for before screenshot
            session_id: Session ID for browser state persistence

        Returns:
            ScrapeResult with vision_extraction populated
        """
        if not extract_prompt:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error="extract_prompt is required for visual extraction",
                error_type="InvalidArgument",
            )

        # Step 1: Capture screenshot using browser tier
        browser_result = await self._capture_screenshot(
            url=url,
            proxy=proxy,
            screenshot_source=screenshot_source,
            full_page=full_page,
            headers=headers,
            timeout=timeout,
            wait_for=wait_for,
            session_id=session_id,
        )

        if not browser_result.success:
            return browser_result

        # Step 2: Get screenshot data
        screenshot_base64 = browser_result.screenshot_base64
        if not screenshot_base64:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error="Failed to capture screenshot",
                error_type="ScreenshotError",
                html=browser_result.html,
                markdown=browser_result.markdown,
            )

        # Step 3: Extract with vision LLM
        extraction_result = await self.vision_router.extract_from_image(
            image_base64=screenshot_base64,
            extraction_prompt=extract_prompt,
            schema=extract_schema,
        )

        if not extraction_result.get("success"):
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error=extraction_result.get("error", "Vision extraction failed"),
                error_type="VisionExtractionError",
                html=browser_result.html,
                markdown=browser_result.markdown,
                screenshot_base64=screenshot_base64,
            )

        # Step 4: Return combined result
        return ScrapeResult(
            success=True,
            tier_used=self.TIER_NUMBER,
            status_code=browser_result.status_code,
            url=url,
            final_url=browser_result.final_url,
            html=browser_result.html,
            markdown=browser_result.markdown,
            vision_extraction=extraction_result.get("data"),
            extracted_data=extraction_result.get("data"),  # Also set extracted_data for compatibility
            screenshot_base64=screenshot_base64,
            screenshot_path=browser_result.screenshot_path,
            cookies=browser_result.cookies,
            session_id=browser_result.session_id,
            metadata={
                **browser_result.metadata,
                "vision_model": extraction_result.get("model"),
                "screenshot_source": screenshot_source,
                "full_page": full_page,
            },
        )

    async def _capture_screenshot(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        screenshot_source: str,
        full_page: bool,
        headers: Optional[dict],
        timeout: int,
        wait_for: Optional[str],
        session_id: Optional[str],
    ) -> ScrapeResult:
        """Capture screenshot using specified browser tier."""
        if screenshot_source == "tier2.5":
            from tiers.tier2_5_agentbrowser import Tier2_5AgentBrowser
            tier = Tier2_5AgentBrowser()
        else:
            from tiers.tier3_camoufox import Tier3Camoufox
            tier = Tier3Camoufox()

        # Fetch with screenshot enabled
        result = await tier.fetch(
            url=url,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            wait_for=wait_for,
            session_id=session_id,
            screenshot=True,
            full_page=full_page,
        )

        return result

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """Tier 5 can handle any URL but requires extraction prompt."""
        return True
