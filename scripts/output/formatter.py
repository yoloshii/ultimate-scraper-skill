"""Output formatting for scraping results."""

import json
import re
from typing import Literal
from core.result import ScrapeResult

OutputFormat = Literal["markdown", "json", "raw"]


class OutputFormatter:
    """Format scraping results for different output modes."""

    @staticmethod
    def format(result: ScrapeResult, output_format: OutputFormat = "markdown") -> str:
        """Format result based on output mode."""
        if output_format == "json":
            return OutputFormatter.to_json(result)
        elif output_format == "raw":
            return OutputFormatter.to_raw(result)
        else:
            return OutputFormatter.to_markdown(result)

    @staticmethod
    def to_markdown(result: ScrapeResult) -> str:
        """Format result as markdown."""
        if not result.success:
            return f"# Error\n\n**Error**: {result.error}\n**Type**: {result.error_type}"

        output = []

        # Header with metadata
        output.append(f"# {result.url}\n")
        output.append(f"**Status**: {result.status_code} | **Tier**: {result.tier_used}")
        if result.from_cache:
            output.append(" | **Cached**")
        output.append(f"\n**Fetched**: {result.fetched_at}\n")

        # Static data (if extracted)
        if result.static_data:
            output.append("\n## Extracted Static Data\n")
            output.append("```json\n")
            output.append(json.dumps(result.static_data, indent=2, default=str)[:5000])
            if len(json.dumps(result.static_data)) > 5000:
                output.append("\n... (truncated)")
            output.append("\n```\n")

        # AI extracted data
        if result.extracted_data:
            output.append("\n## AI Extracted Data\n")
            output.append("```json\n")
            output.append(json.dumps(result.extracted_data, indent=2, default=str))
            output.append("\n```\n")

        # Main content
        if result.markdown:
            output.append("\n## Content\n\n")
            output.append(result.markdown)
        elif result.html:
            output.append("\n## Raw HTML (excerpt)\n\n```html\n")
            output.append(result.html[:5000])
            if len(result.html) > 5000:
                output.append("\n... (truncated)")
            output.append("\n```\n")

        return "".join(output)

    @staticmethod
    def to_json(result: ScrapeResult) -> str:
        """Format result as JSON."""
        data = result.to_dict()

        # Include content based on what's available
        if result.extracted_data:
            data["data"] = result.extracted_data
        elif result.static_data:
            data["data"] = result.static_data

        # Truncate large content for JSON output
        if result.markdown and len(result.markdown) > 50000:
            data["markdown"] = result.markdown[:50000] + "... (truncated)"
        else:
            data["markdown"] = result.markdown

        # Exclude raw HTML from JSON output (too large)
        data.pop("html", None)

        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def to_raw(result: ScrapeResult) -> str:
        """Return raw HTML content."""
        if not result.success:
            return f"Error: {result.error}"
        return result.html or result.raw or result.markdown

    @staticmethod
    def html_to_markdown(html: str) -> str:
        """Convert HTML to markdown using html2text."""
        try:
            import html2text
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_emphasis = False
            h.body_width = 0  # Don't wrap lines
            h.unicode_snob = True
            h.skip_internal_links = True
            return h.handle(html)
        except ImportError:
            # Fallback: basic HTML stripping
            return OutputFormatter._basic_html_strip(html)

    @staticmethod
    def _basic_html_strip(html: str) -> str:
        """Basic HTML to text conversion without dependencies."""
        # Remove scripts and styles
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Convert common elements
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<p[^>]*>', '\n\n', html, flags=re.IGNORECASE)
        html = re.sub(r'</p>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<h([1-6])[^>]*>(.*?)</h\1>', r'\n\n## \2\n\n', html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r'<li[^>]*>', '\n- ', html, flags=re.IGNORECASE)

        # Remove remaining tags
        html = re.sub(r'<[^>]+>', '', html)

        # Clean up whitespace
        html = re.sub(r'\n\s*\n', '\n\n', html)
        html = re.sub(r' +', ' ', html)

        # Decode HTML entities
        import html as html_module
        html = html_module.unescape(html)

        return html.strip()

    @staticmethod
    def truncate_content(content: str, max_tokens: int = 100000) -> str:
        """Truncate content to approximate token limit (rough estimate: 4 chars per token)."""
        max_chars = max_tokens * 4
        if len(content) <= max_chars:
            return content
        return content[:max_chars] + f"\n\n... (truncated, {len(content)} chars total)"
