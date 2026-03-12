"""Tier 0: Static extraction without HTTP request (for pre-fetched HTML)."""

from typing import Optional
from tiers.base import BaseTier
from core.result import ScrapeResult
from extraction.static import StaticExtractor
from output.formatter import OutputFormatter
from proxy.manager import ProxyConfig


class Tier0Static(BaseTier):
    """
    Tier 0: Static data extraction.

    Extracts embedded JSON data from HTML without making HTTP requests.
    Use when HTML is already available (from cache or higher tier).

    Extracts:
    - __NEXT_DATA__ (Next.js)
    - __NUXT__ (Nuxt.js)
    - JSON-LD (Schema.org)
    - __APOLLO_STATE__ (GraphQL)
    - Other window.* variables
    """

    TIER_NUMBER = 0
    TIER_NAME = "static"

    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
        html: Optional[str] = None,
        **kwargs,
    ) -> ScrapeResult:
        """
        Extract static data from provided HTML.

        Args:
            url: Original URL (for metadata)
            proxy: Not used in Tier 0
            headers: Not used in Tier 0
            timeout: Not used in Tier 0
            html: Pre-fetched HTML content to extract from

        Returns:
            ScrapeResult with extracted static data
        """
        if not html:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                error="No HTML provided for static extraction",
                error_type="NoContent",
            )

        try:
            # Extract all static data
            static_data = StaticExtractor.extract_all(html)

            if not static_data:
                return ScrapeResult(
                    success=False,
                    tier_used=self.TIER_NUMBER,
                    url=url,
                    html=html,
                    error="No static data found in HTML",
                    error_type="NoStaticData",
                )

            # Extract meta tags
            meta = StaticExtractor.extract_meta_tags(html)
            if meta:
                static_data["meta"] = meta

            # Convert HTML to markdown
            markdown = OutputFormatter.html_to_markdown(html)

            return ScrapeResult(
                success=True,
                tier_used=self.TIER_NUMBER,
                status_code=200,
                url=url,
                html=html,
                markdown=markdown,
                static_data=static_data,
                metadata={
                    "extraction_method": "static",
                    "data_sources": list(static_data.keys()),
                },
            )

        except Exception as e:
            return ScrapeResult(
                success=False,
                tier_used=self.TIER_NUMBER,
                url=url,
                html=html,
                error=str(e),
                error_type=type(e).__name__,
            )

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """
        Static extraction can handle any URL if HTML is provided.
        """
        return True

    @staticmethod
    def probe(html: str) -> dict:
        """
        Probe HTML to see what static data is available.

        Returns:
            Dict with available data types and their sizes
        """
        result = {
            "has_static_data": StaticExtractor.has_static_data(html),
            "sources": [],
        }

        if "__NEXT_DATA__" in html:
            result["sources"].append("next_data")
        if "__NUXT__" in html:
            result["sources"].append("nuxt_data")
        if "application/ld+json" in html:
            result["sources"].append("json_ld")
        if "__APOLLO_STATE__" in html:
            result["sources"].append("apollo_state")

        return result
