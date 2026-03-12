"""Static data extraction from HTML (no JavaScript execution)."""

import re
import json
from typing import Optional, Any
from bs4 import BeautifulSoup


class StaticExtractor:
    """Extract embedded data from HTML without JavaScript execution."""

    @staticmethod
    def extract_all(html: str) -> dict:
        """
        Extract all available static data from HTML.

        Returns dict with keys: next_data, nuxt_data, json_ld, apollo_state, etc.
        """
        result = {}

        # Next.js
        next_data = StaticExtractor.extract_next_data(html)
        if next_data:
            result["next_data"] = next_data

        # Nuxt.js
        nuxt_data = StaticExtractor.extract_nuxt_data(html)
        if nuxt_data:
            result["nuxt_data"] = nuxt_data

        # JSON-LD (Schema.org)
        json_ld = StaticExtractor.extract_json_ld(html)
        if json_ld:
            result["json_ld"] = json_ld

        # Apollo GraphQL state
        apollo_state = StaticExtractor.extract_apollo_state(html)
        if apollo_state:
            result["apollo_state"] = apollo_state

        # Remix data
        remix_data = StaticExtractor.extract_remix_data(html)
        if remix_data:
            result["remix_data"] = remix_data

        # Generic window variables
        window_vars = StaticExtractor.extract_window_vars(html)
        if window_vars:
            result["window_vars"] = window_vars

        return result

    @staticmethod
    def extract_next_data(html: str) -> Optional[dict]:
        """Extract __NEXT_DATA__ from Next.js pages."""
        try:
            # Method 1: BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            script = soup.find("script", {"id": "__NEXT_DATA__"})
            if script and script.string:
                return json.loads(script.string)

            # Method 2: Regex fallback
            pattern = r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>'
            match = re.search(pattern, html, re.DOTALL)
            if match:
                return json.loads(match.group(1))

        except (json.JSONDecodeError, Exception):
            pass
        return None

    @staticmethod
    def extract_nuxt_data(html: str) -> Optional[dict]:
        """Extract __NUXT__ from Nuxt.js pages."""
        try:
            # Try chompjs for JavaScript object parsing
            try:
                import chompjs
                pattern = r'window\.__NUXT__\s*=\s*({.*?});?\s*(?:</script>|$)'
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    return chompjs.parse_js_object(match.group(1))
            except ImportError:
                pass

            # Fallback: Simple JSON extraction
            pattern = r'window\.__NUXT__\s*=\s*(\{[^;]+\})'
            match = re.search(pattern, html, re.DOTALL)
            if match:
                # Try to parse as JSON (may fail for JS objects)
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

        except Exception:
            pass
        return None

    @staticmethod
    def extract_json_ld(html: str) -> list[dict]:
        """Extract all JSON-LD (Schema.org) data from page."""
        results = []
        try:
            soup = BeautifulSoup(html, "lxml")
            scripts = soup.find_all("script", {"type": "application/ld+json"})

            for script in scripts:
                if script.string:
                    try:
                        data = json.loads(script.string)
                        if isinstance(data, list):
                            results.extend(data)
                        else:
                            results.append(data)
                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass
        return results

    @staticmethod
    def extract_apollo_state(html: str) -> Optional[dict]:
        """Extract Apollo GraphQL cache state."""
        try:
            # Try chompjs first
            try:
                import chompjs
                pattern = r'window\.__APOLLO_STATE__\s*=\s*({.*?});?\s*(?:</script>|$)'
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    return chompjs.parse_js_object(match.group(1))
            except ImportError:
                pass

            # Fallback patterns
            patterns = [
                r'<script>window\.__APOLLO_STATE__\s*=\s*({.+?});</script>',
                r'"__APOLLO_STATE__"\s*:\s*({.+?})\s*[,}]',
            ]

            for pattern in patterns:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        return json.loads(match.group(1))
                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass
        return None

    @staticmethod
    def extract_remix_data(html: str) -> Optional[dict]:
        """Extract Remix framework data."""
        try:
            soup = BeautifulSoup(html, "lxml")

            # Remix uses script tags with type="application/json"
            scripts = soup.find_all("script", {"type": "application/json"})
            for script in scripts:
                if script.string and "__remixContext" in html:
                    try:
                        return json.loads(script.string)
                    except json.JSONDecodeError:
                        continue

        except Exception:
            pass
        return None

    @staticmethod
    def extract_window_vars(html: str, var_names: Optional[list[str]] = None) -> dict:
        """
        Extract common window.* variables.

        Args:
            html: HTML content
            var_names: Specific variable names to look for (optional)

        Returns:
            Dict of variable name -> parsed value
        """
        results = {}

        # Default common variables
        default_vars = [
            "__INITIAL_STATE__",
            "__PRELOADED_STATE__",
            "__DATA__",
            "__INITIAL_DATA__",
            "__APP_STATE__",
            "__STORE__",
        ]

        var_names = var_names or default_vars

        try:
            import chompjs
            has_chompjs = True
        except ImportError:
            has_chompjs = False

        for var_name in var_names:
            try:
                pattern = rf'window\.{re.escape(var_name)}\s*=\s*({{\s*.*?\s*}});?\s*(?:</script>|$)'
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    if has_chompjs:
                        results[var_name] = chompjs.parse_js_object(match.group(1))
                    else:
                        try:
                            results[var_name] = json.loads(match.group(1))
                        except json.JSONDecodeError:
                            pass
            except Exception:
                continue

        return results

    @staticmethod
    def extract_meta_tags(html: str) -> dict:
        """Extract Open Graph and other meta tags."""
        result = {
            "og": {},
            "twitter": {},
            "meta": {},
        }

        try:
            soup = BeautifulSoup(html, "lxml")

            # Open Graph tags
            for tag in soup.find_all("meta", property=re.compile(r"^og:")):
                prop = tag.get("property", "").replace("og:", "")
                result["og"][prop] = tag.get("content", "")

            # Twitter tags
            for tag in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")}):
                name = tag.get("name", "").replace("twitter:", "")
                result["twitter"][name] = tag.get("content", "")

            # Standard meta tags
            for name in ["description", "keywords", "author", "robots"]:
                tag = soup.find("meta", attrs={"name": name})
                if tag:
                    result["meta"][name] = tag.get("content", "")

            # Title
            title = soup.find("title")
            if title:
                result["meta"]["title"] = title.get_text(strip=True)

        except Exception:
            pass

        return result

    @staticmethod
    def has_static_data(html: str) -> bool:
        """Quick check if HTML contains extractable static data."""
        indicators = [
            "__NEXT_DATA__",
            "__NUXT__",
            "application/ld+json",
            "__APOLLO_STATE__",
            "__INITIAL_STATE__",
            "__PRELOADED_STATE__",
        ]
        return any(indicator in html for indicator in indicators)
