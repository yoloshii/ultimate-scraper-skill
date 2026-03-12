"""Unit tests for WebMCP extraction module."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from extraction.webmcp import WEBMCP_INIT_SCRIPT


class TestWebMCPInitScript:
    """Tests for WEBMCP_INIT_SCRIPT validity."""

    def test_script_is_iife(self):
        """Init script is an IIFE."""
        stripped = WEBMCP_INIT_SCRIPT.strip()
        assert stripped.startswith("(")
        assert stripped.endswith(");")

    def test_initializes_webmcp_namespace(self):
        """Script creates window.__webmcp namespace."""
        assert "window.__webmcp" in WEBMCP_INIT_SCRIPT

    def test_intercepts_register_tool(self):
        """Script intercepts navigator.modelContext.registerTool."""
        assert "registerTool" in WEBMCP_INIT_SCRIPT

    def test_no_provide_context(self):
        """Script does NOT reference provideContext (removed in Chrome 147, spec PR #132)."""
        # provideContext/clearContext were removed from the spec
        # Our init script must not call .bind() on non-existent methods
        assert ".provideContext" not in WEBMCP_INIT_SCRIPT
        assert ".clearContext" not in WEBMCP_INIT_SCRIPT

    def test_captures_read_only_hint(self):
        """Script captures readOnlyHint from ToolAnnotations."""
        assert "readOnlyHint" in WEBMCP_INIT_SCRIPT

    def test_provides_mock_client(self):
        """Script provides mockClient with requestUserInteraction for execute callback."""
        assert "requestUserInteraction" in WEBMCP_INIT_SCRIPT
        assert "mockClient" in WEBMCP_INIT_SCRIPT

    def test_checks_register_tool_existence(self):
        """Script checks registerTool exists before binding."""
        assert "typeof navigator.modelContext.registerTool" in WEBMCP_INIT_SCRIPT

    def test_scans_declarative_forms(self):
        """Script scans declarative <form toolname> elements."""
        assert "form[toolname]" in WEBMCP_INIT_SCRIPT

    def test_exposes_execute_helper(self):
        """Script exposes window.__webmcp.executeTool."""
        assert "executeTool" in WEBMCP_INIT_SCRIPT

    def test_rescan_declarative_exposed(self):
        """Script exposes rescanDeclarative function."""
        assert "rescanDeclarative" in WEBMCP_INIT_SCRIPT


class TestWebMCPExecuteTool:
    """Tests for execute_tool safety."""

    def test_no_string_interpolation(self):
        """execute_tool uses parameterized evaluate, not string interpolation."""
        from extraction.webmcp import execute_tool
        import inspect
        source = inspect.getsource(execute_tool)
        # Should not use f-string with tool_name
        assert "f\"" not in source or "tool_name" not in source.split("f\"")[1] if "f\"" in source else True
        # Should pass as array argument
        assert "[tool_name, args]" in source
