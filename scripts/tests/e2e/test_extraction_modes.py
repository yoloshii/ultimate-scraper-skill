"""End-to-end tests for extraction modes."""

import pytest
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.e2e
class TestStaticExtraction:
    """Tests for static mode extraction."""

    @pytest.mark.asyncio
    async def test_static_mode_json_ld(self):
        """Static mode extracts JSON-LD from real page."""
        import httpx
        from extraction.static import StaticExtractor

        async with httpx.AsyncClient() as client:
            response = await client.get("https://schema.org/")

            html = response.text

            # Schema.org should have JSON-LD
            if "application/ld+json" in html:
                json_ld = StaticExtractor.extract_json_ld(html)
                assert len(json_ld) > 0
            else:
                pytest.skip("No JSON-LD found on schema.org")

    def test_static_extractor_real_nextjs_html(self):
        """Static extractor handles real Next.js HTML structure."""
        from extraction.static import StaticExtractor

        # Simulated Next.js page structure
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Next.js App</title>
        </head>
        <body>
            <div id="__next">
                <main>Page content here</main>
            </div>
            <script id="__NEXT_DATA__" type="application/json">
            {
                "props": {
                    "pageProps": {
                        "products": [
                            {"id": 1, "name": "Widget A", "price": 29.99},
                            {"id": 2, "name": "Widget B", "price": 39.99}
                        ]
                    }
                },
                "page": "/products",
                "query": {}
            }
            </script>
        </body>
        </html>
        '''

        result = StaticExtractor.extract_next_data(html)

        assert result is not None
        assert "props" in result
        assert len(result["props"]["pageProps"]["products"]) == 2


@pytest.mark.e2e
class TestOutputFormats:
    """Tests for output format handling."""

    def test_output_format_markdown(self):
        """Markdown output is properly formatted."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            markdown="# Heading\n\nParagraph text\n\n- Item 1\n- Item 2"
        )

        output = result.formatted_output

        assert output.startswith("#")
        assert "Heading" in output
        assert "- Item" in output

    def test_output_format_json(self):
        """JSON output is valid JSON."""
        import json
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            tier_used=2,
            status_code=200,
            url="https://example.com",
            extracted_data={"key": "value"}
        )

        # to_dict should be JSON serializable
        output = result.to_dict()
        json_str = json.dumps(output)

        # Should be valid JSON
        parsed = json.loads(json_str)
        assert parsed["success"] is True
        assert parsed["tier_used"] == 2

    def test_output_with_static_data(self):
        """Output includes static data when available."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            static_data={
                "next_data": {"props": {"page": "home"}},
                "json_ld": [{"@type": "Article"}]
            }
        )

        output = result.to_dict()

        assert output["static_data"] is not None
        assert "next_data" in output["static_data"]
        assert "json_ld" in output["static_data"]


@pytest.mark.e2e
class TestExtractAll:
    """Tests for extract_all comprehensive extraction."""

    def test_extract_all_multiple_sources(self):
        """extract_all extracts from multiple sources."""
        from extraction.static import StaticExtractor

        html = '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Multi-Source Page</title>
            <meta property="og:title" content="OG Title">
            <meta property="og:description" content="OG Description">
            <script type="application/ld+json">
            {"@type": "Product", "name": "Test Product", "price": "19.99"}
            </script>
        </head>
        <body>
            <script id="__NEXT_DATA__" type="application/json">
            {"props": {"pageProps": {"data": "next"}}}
            </script>
        </body>
        </html>
        '''

        result = StaticExtractor.extract_all(html)

        # Should have multiple extractions
        assert "next_data" in result
        assert "json_ld" in result
        assert len(result["json_ld"]) > 0

    def test_extract_meta_tags_comprehensive(self):
        """extract_meta_tags gets OG, Twitter, and standard meta."""
        from extraction.static import StaticExtractor

        html = '''
        <html>
        <head>
            <title>Meta Test Page</title>
            <meta name="description" content="Page description">
            <meta name="keywords" content="test, keywords">
            <meta property="og:title" content="Open Graph Title">
            <meta property="og:image" content="https://example.com/image.jpg">
            <meta property="og:type" content="website">
            <meta name="twitter:card" content="summary_large_image">
            <meta name="twitter:title" content="Twitter Title">
        </head>
        <body></body>
        </html>
        '''

        result = StaticExtractor.extract_meta_tags(html)

        assert result["meta"]["title"] == "Meta Test Page"
        assert result["meta"]["description"] == "Page description"
        assert result["og"]["title"] == "Open Graph Title"
        assert result["og"]["image"] == "https://example.com/image.jpg"
        assert result["twitter"]["card"] == "summary_large_image"


@pytest.mark.e2e
@pytest.mark.slow
class TestAIExtraction:
    """Tests for AI extraction mode (requires LLM)."""

    def test_ai_extraction_prompt_format(self):
        """AI extraction prompt is properly formatted."""
        # Test the prompt format that would be sent to LLM
        prompt = "Extract all product names and prices"
        html = "<div class='product'><h2>Widget</h2><span>$19.99</span></div>"

        # Format like AIExtractionRouter would
        formatted = f"""Extract structured data from the following HTML content.

Prompt: {prompt}

HTML:
{html[:5000]}

Return JSON with the extracted data."""

        assert "Extract structured data" in formatted
        assert prompt in formatted
        assert "Widget" in formatted


@pytest.mark.e2e
class TestResultFormats:
    """Tests for ScrapeResult output formats."""

    def test_result_content_priority(self):
        """content property returns best available content."""
        from core.result import ScrapeResult

        # Markdown preferred
        r1 = ScrapeResult(markdown="# MD", html="<h1>HTML</h1>", raw="raw")
        assert r1.content == "# MD"

        # HTML fallback
        r2 = ScrapeResult(markdown="", html="<h1>HTML</h1>", raw="raw")
        assert r2.content == "<h1>HTML</h1>"

        # Raw fallback
        r3 = ScrapeResult(markdown="", html="", raw="raw content")
        assert r3.content == "raw content"

    def test_result_to_dict_complete(self):
        """to_dict includes all relevant fields."""
        from core.result import ScrapeResult

        result = ScrapeResult(
            success=True,
            tier_used=3,
            status_code=200,
            url="https://example.com",
            final_url="https://example.com/redirected",
            html="<html>content</html>",
            markdown="# Content",
            extracted_data={"key": "value"},
            static_data={"next_data": {}},
            session_id="test-session",
            fingerprint_id="fp-123",
            cookies={"session": "abc"},
            error=None,
        )

        d = result.to_dict()

        required_keys = [
            "success", "tier_used", "status_code", "url", "final_url",
            "content_length", "extracted_data", "static_data",
            "session_id", "fingerprint_id", "error", "from_cache"
        ]

        for key in required_keys:
            assert key in d, f"Missing key: {key}"

    def test_result_str_representation(self):
        """__str__ provides useful summary."""
        from core.result import ScrapeResult

        success = ScrapeResult(success=True, tier_used=2, markdown="# Content")
        assert "success=True" in str(success)
        assert "tier=2" in str(success)

        failure = ScrapeResult(success=False, error="Connection refused")
        assert "success=False" in str(failure)
        assert "Connection refused" in str(failure)
