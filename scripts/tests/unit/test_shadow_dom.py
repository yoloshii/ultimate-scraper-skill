"""Unit tests for Shadow DOM piercing module."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from extraction.shadow_dom import DEEP_QUERY_JS


class TestDeepQueryJS:
    """Tests for DEEP_QUERY_JS validity."""

    def test_defines_deep_query(self):
        """JS defines deepQuery function."""
        assert "deepQuery" in DEEP_QUERY_JS

    def test_defines_deep_query_all(self):
        """JS defines deepQueryAll function."""
        assert "deepQueryAll" in DEEP_QUERY_JS

    def test_traverses_shadow_root(self):
        """JS traverses shadowRoot for piercing."""
        assert "shadowRoot" in DEEP_QUERY_JS

    def test_queries_all_elements(self):
        """JS uses querySelectorAll for recursive search."""
        assert "querySelectorAll" in DEEP_QUERY_JS
