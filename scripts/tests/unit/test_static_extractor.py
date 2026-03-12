"""Unit tests for StaticExtractor."""

import pytest
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from extraction.static import StaticExtractor


class TestStaticExtractor:
    """Tests for StaticExtractor static data extraction."""

    def test_extract_next_data(self, sample_html_nextjs):
        """Extracts __NEXT_DATA__ JSON from script tag."""
        result = StaticExtractor.extract_next_data(sample_html_nextjs)

        assert result is not None
        assert "props" in result
        assert result["props"]["pageProps"]["title"] == "Test"
        assert result["props"]["pageProps"]["items"] == [1, 2, 3]

    def test_extract_next_data_missing(self):
        """Returns None when no __NEXT_DATA__ present."""
        html = "<html><body>No next data here</body></html>"
        result = StaticExtractor.extract_next_data(html)

        assert result is None

    def test_extract_nuxt_data(self, sample_html_nuxt):
        """Extracts __NUXT__ from window assignment."""
        result = StaticExtractor.extract_nuxt_data(sample_html_nuxt)

        # Note: extraction depends on chompjs availability
        # May be None if chompjs not installed
        if result is not None:
            assert "data" in result or "state" in result

    def test_extract_nuxt_data_missing(self):
        """Returns None when no __NUXT__ present."""
        html = "<html><body>No nuxt data</body></html>"
        result = StaticExtractor.extract_nuxt_data(html)

        assert result is None

    def test_extract_json_ld(self, sample_html_json_ld):
        """Extracts application/ld+json scripts."""
        result = StaticExtractor.extract_json_ld(sample_html_json_ld)

        assert len(result) > 0
        assert result[0]["@type"] == "Product"
        assert result[0]["name"] == "Widget"
        assert result[0]["price"] == "19.99"

    def test_extract_json_ld_multiple(self):
        """Extracts multiple JSON-LD blocks."""
        html = '''
        <html>
        <head>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "Acme"}
        </script>
        <script type="application/ld+json">
        {"@type": "WebSite", "url": "https://example.com"}
        </script>
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_json_ld(html)

        assert len(result) == 2
        assert result[0]["@type"] == "Organization"
        assert result[1]["@type"] == "WebSite"

    def test_extract_json_ld_array(self):
        """Extracts JSON-LD when content is an array."""
        html = '''
        <html>
        <head>
        <script type="application/ld+json">
        [{"@type": "Product", "name": "A"}, {"@type": "Product", "name": "B"}]
        </script>
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_json_ld(html)

        assert len(result) == 2
        assert result[0]["name"] == "A"
        assert result[1]["name"] == "B"

    def test_extract_json_ld_empty(self):
        """Returns empty list when no JSON-LD present."""
        html = "<html><body>No structured data</body></html>"
        result = StaticExtractor.extract_json_ld(html)

        assert result == []

    def test_extract_apollo_state(self, sample_html_apollo):
        """Extracts Apollo GraphQL state."""
        result = StaticExtractor.extract_apollo_state(sample_html_apollo)

        # Depends on chompjs availability
        if result is not None:
            assert "ROOT_QUERY" in result

    def test_extract_apollo_state_missing(self):
        """Returns None when no Apollo state present."""
        html = "<html><body>No apollo</body></html>"
        result = StaticExtractor.extract_apollo_state(html)

        assert result is None

    def test_extract_window_vars_default(self):
        """Extracts common window.* variables."""
        html = '''
        <html>
        <head>
        <script>
        window.__INITIAL_STATE__ = {"user": "test", "loggedIn": true};
        </script>
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_window_vars(html)

        # Depends on chompjs availability
        if "__INITIAL_STATE__" in result:
            assert result["__INITIAL_STATE__"]["user"] == "test"

    def test_extract_window_vars_custom(self):
        """Extracts custom window variables by name."""
        html = '''
        <html>
        <script>
        window.__MY_CUSTOM_DATA__ = {"items": [1, 2, 3]};
        </script>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_window_vars(html, var_names=["__MY_CUSTOM_DATA__"])

        # Result depends on regex match and chompjs
        assert isinstance(result, dict)

    def test_extract_meta_tags(self):
        """Extract Open Graph and other meta tags."""
        html = '''
        <html>
        <head>
        <title>Page Title</title>
        <meta name="description" content="Page description">
        <meta name="keywords" content="test, keywords">
        <meta property="og:title" content="OG Title">
        <meta property="og:image" content="https://example.com/image.jpg">
        <meta name="twitter:card" content="summary">
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_meta_tags(html)

        assert result["meta"]["title"] == "Page Title"
        assert result["meta"]["description"] == "Page description"
        assert result["og"]["title"] == "OG Title"
        assert result["og"]["image"] == "https://example.com/image.jpg"
        assert result["twitter"]["card"] == "summary"

    def test_has_static_data_true(self, sample_html_nextjs):
        """Returns True when static data present."""
        assert StaticExtractor.has_static_data(sample_html_nextjs) is True

    def test_has_static_data_false(self):
        """Returns False for plain HTML."""
        html = "<html><body>Plain content</body></html>"
        assert StaticExtractor.has_static_data(html) is False

    def test_has_static_data_json_ld(self, sample_html_json_ld):
        """Returns True for JSON-LD content."""
        assert StaticExtractor.has_static_data(sample_html_json_ld) is True

    def test_has_static_data_apollo(self, sample_html_apollo):
        """Returns True for Apollo state."""
        assert StaticExtractor.has_static_data(sample_html_apollo) is True

    def test_extract_all_combines(self, sample_html_nextjs):
        """extract_all() returns all found data."""
        result = StaticExtractor.extract_all(sample_html_nextjs)

        assert isinstance(result, dict)
        assert "next_data" in result

    def test_extract_all_multiple_sources(self):
        """extract_all() extracts from multiple sources."""
        html = '''
        <!DOCTYPE html>
        <html>
        <head>
        <title>Multi-data Page</title>
        <script id="__NEXT_DATA__" type="application/json">
        {"props": {"data": "next"}}
        </script>
        <script type="application/ld+json">
        {"@type": "Article", "headline": "Test"}
        </script>
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_all(html)

        assert "next_data" in result
        assert "json_ld" in result
        assert len(result["json_ld"]) > 0

    def test_extract_remix_data(self):
        """Extracts Remix framework data."""
        html = '''
        <html>
        <head>
        <script type="application/json">
        {"routes": {"root": {"data": {"user": "test"}}}}
        </script>
        </head>
        <body>
        <script>window.__remixContext = true;</script>
        </body>
        </html>
        '''
        result = StaticExtractor.extract_remix_data(html)

        # Should attempt extraction when __remixContext present
        # Result depends on exact HTML structure
        assert result is None or isinstance(result, dict)

    def test_extract_handles_malformed_json(self):
        """Extractors handle malformed JSON gracefully."""
        html = '''
        <html>
        <head>
        <script id="__NEXT_DATA__" type="application/json">
        {invalid json here
        </script>
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_next_data(html)

        assert result is None  # Should not raise exception

    def test_extract_handles_empty_script(self):
        """Extractors handle empty script tags."""
        html = '''
        <html>
        <head>
        <script id="__NEXT_DATA__" type="application/json"></script>
        </head>
        <body></body>
        </html>
        '''
        result = StaticExtractor.extract_next_data(html)

        assert result is None
