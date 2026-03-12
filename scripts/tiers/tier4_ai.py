"""Tier 4: AI-assisted extraction via Crawl4AI."""

import asyncio
from typing import Optional
from tiers.base import BaseTier
from core.result import ScrapeResult
from core.config import get_config
from extraction.static import StaticExtractor
from extraction.ai_router import AIExtractionRouter
from output.formatter import OutputFormatter
from proxy.manager import ProxyConfig, ProxyEmpireManager


class Tier4AI(BaseTier):
    """
    Tier 4: AI-assisted web scraping and extraction.

    Uses Crawl4AI for intelligent content extraction with LLM support,
    or falls back to Tier 3 + AIExtractionRouter for extraction.

    Features:
    - LLM-powered content extraction
    - Natural language extraction prompts
    - Schema-based structured output
    - BM25 content filtering
    - Deep crawl support
    """

    TIER_NUMBER = 4
    TIER_NAME = "ai"

    def __init__(self):
        self.proxy_manager = ProxyEmpireManager()
        self.ai_router = AIExtractionRouter()
        self.config = get_config()

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 60,
        extract_prompt: Optional[str] = None,
        schema: Optional[dict] = None,
        use_crawl4ai: bool = True,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch and extract data with AI assistance.

        Args:
            url: Target URL
            proxy: Optional proxy configuration
            headers: Optional custom headers
            timeout: Request timeout in seconds
            extract_prompt: Natural language extraction instruction
            schema: Optional JSON schema for structured output
            use_crawl4ai: Try Crawl4AI first (otherwise use Tier 3 + AI)

        Returns:
            ScrapeResult with extracted data
        """
        # Try Crawl4AI first if available and requested
        if use_crawl4ai:
            try:
                return await self._fetch_with_crawl4ai(
                    url=url,
                    proxy=proxy,
                    timeout=timeout,
                    extract_prompt=extract_prompt,
                    schema=schema,
                )
            except ImportError:
                pass  # Crawl4AI not installed, fall back
            except Exception as e:
                # If Crawl4AI fails, fall back to Tier 3 + AI extraction
                pass

        # Fallback: Use Tier 3 (Camoufox) for fetching, then AI for extraction
        return await self._fetch_with_tier3_and_ai(
            url=url,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
            extract_prompt=extract_prompt,
            schema=schema,
        )

    async def _fetch_with_crawl4ai(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        timeout: int,
        extract_prompt: Optional[str],
        schema: Optional[dict],
    ) -> ScrapeResult:
        """Fetch using Crawl4AI with built-in LLM extraction."""
        from crawl4ai import AsyncWebCrawler
        from crawl4ai.extraction_strategy import LLMExtractionStrategy

        try:
            # Configure extraction strategy if prompt provided
            extraction_strategy = None
            if extract_prompt:
                extraction_strategy = LLMExtractionStrategy(
                    provider="openai/custom",  # Will use our router
                    api_base=self.config.local_llm_url.rsplit("/", 1)[0],
                    instruction=extract_prompt,
                    schema=schema,
                )

            # Configure crawler
            crawler_config = {
                "headless": True,
                "verbose": False,
            }

            # Add proxy if configured
            if proxy:
                crawler_config["proxy"] = proxy.curl_format

            async with AsyncWebCrawler(**crawler_config) as crawler:
                result = await crawler.arun(
                    url=url,
                    extraction_strategy=extraction_strategy,
                    timeout=timeout * 1000,
                )

                if not result.success:
                    return ScrapeResult(
                        success=False,
                        tier_used=self.TIER_NUMBER,
                        url=url,
                        error=result.error_message or "Crawl4AI extraction failed",
                        error_type="ExtractionError",
                    )

                # Get extracted data
                extracted_data = None
                if result.extracted_content:
                    try:
                        import json
                        extracted_data = json.loads(result.extracted_content)
                    except json.JSONDecodeError:
                        extracted_data = {"raw": result.extracted_content}

                # Get static data
                static_data = None
                if result.html and StaticExtractor.has_static_data(result.html):
                    static_data = StaticExtractor.extract_all(result.html)

                return ScrapeResult(
                    success=True,
                    tier_used=self.TIER_NUMBER,
                    status_code=200,
                    url=url,
                    final_url=result.url or url,
                    html=result.html or "",
                    markdown=result.markdown or OutputFormatter.html_to_markdown(result.html or ""),
                    static_data=static_data,
                    extracted_data=extracted_data,
                    metadata={
                        "method": "crawl4ai",
                        "extraction_prompt": extract_prompt,
                        "proxy_geo": proxy.geo if proxy else None,
                    },
                )

        except Exception as e:
            raise

    async def _fetch_with_tier3_and_ai(
        self,
        url: str,
        proxy: Optional[ProxyConfig],
        headers: Optional[dict],
        timeout: int,
        extract_prompt: Optional[str],
        schema: Optional[dict],
    ) -> ScrapeResult:
        """Fallback: Use Tier 3 for fetching, then AI router for extraction."""
        from tiers.tier3_camoufox import Tier3Camoufox

        # First, fetch with Tier 3
        tier3 = Tier3Camoufox()
        result = await tier3.fetch(
            url=url,
            proxy=proxy,
            headers=headers,
            timeout=timeout,
        )

        if not result.success:
            # Tier 3 failed, return the error
            result.tier_used = self.TIER_NUMBER
            return result

        # If no extraction prompt, just return the content
        if not extract_prompt:
            result.tier_used = self.TIER_NUMBER
            result.metadata["method"] = "tier3_only"
            return result

        # Run AI extraction on the content
        content = result.markdown or result.html

        # Truncate content if too long (rough token estimate)
        max_content_chars = 50000  # ~12.5k tokens
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "\n\n... (truncated)"

        extraction_result = await self.ai_router.extract(
            content=content,
            extraction_prompt=extract_prompt,
            schema=schema,
        )

        if extraction_result.get("success"):
            result.extracted_data = extraction_result.get("data")
            result.metadata["extraction_model"] = extraction_result.get("model")
            result.metadata["extraction_tier"] = extraction_result.get("tier")
        else:
            result.metadata["extraction_error"] = extraction_result.get("error")

        result.tier_used = self.TIER_NUMBER
        result.metadata["method"] = "tier3_plus_ai"
        result.metadata["extraction_prompt"] = extract_prompt

        return result

    async def extract_from_html(
        self,
        html: str,
        extract_prompt: str,
        schema: Optional[dict] = None,
        url: str = "",
    ) -> ScrapeResult:
        """
        Extract data from pre-fetched HTML.

        Args:
            html: HTML content to extract from
            extract_prompt: Natural language extraction instruction
            schema: Optional JSON schema for structured output
            url: Original URL (for metadata)

        Returns:
            ScrapeResult with extracted data
        """
        # Convert to markdown first
        markdown = OutputFormatter.html_to_markdown(html)

        # Truncate if too long
        content = markdown
        max_content_chars = 50000
        if len(content) > max_content_chars:
            content = content[:max_content_chars] + "\n\n... (truncated)"

        # Run extraction
        extraction_result = await self.ai_router.extract(
            content=content,
            extraction_prompt=extract_prompt,
            schema=schema,
        )

        # Get static data
        static_data = None
        if StaticExtractor.has_static_data(html):
            static_data = StaticExtractor.extract_all(html)

        if extraction_result.get("success"):
            return ScrapeResult(
                success=True,
                tier_used=self.TIER_NUMBER,
                status_code=200,
                url=url,
                html=html,
                markdown=markdown,
                static_data=static_data,
                extracted_data=extraction_result.get("data"),
                metadata={
                    "method": "extract_from_html",
                    "extraction_model": extraction_result.get("model"),
                    "extraction_tier": extraction_result.get("tier"),
                    "extraction_prompt": extract_prompt,
                },
            )
        else:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                html=html,
                markdown=markdown,
                static_data=static_data,
                error=extraction_result.get("error"),
                error_type="ExtractionError",
            )

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """
        Tier 4 can handle any URL (uses lower tiers for fetching).
        """
        return True
