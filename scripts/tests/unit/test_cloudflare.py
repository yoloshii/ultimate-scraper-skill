"""Tests for Cloudflare detection and parsing utilities."""

import pytest
from detection.cloudflare import (
    parse_content_signal,
    parse_markdown_tokens,
    is_cf_markdown_response,
    extract_cf_headers,
    parse_rfc9457_error,
)


class TestParseContentSignal:
    """Tests for Content-Signal header parsing."""

    def test_full_signal(self):
        result = parse_content_signal("ai-train=yes, search=yes, ai-input=yes")
        assert result == {"ai_train": True, "search": True, "ai_input": True}

    def test_mixed_permissions(self):
        result = parse_content_signal("ai-train=no, search=yes, ai-input=no")
        assert result == {"ai_train": False, "search": True, "ai_input": False}

    def test_all_no(self):
        result = parse_content_signal("ai-train=no, search=no, ai-input=no")
        assert result == {"ai_train": False, "search": False, "ai_input": False}

    def test_empty_string(self):
        assert parse_content_signal("") == {}

    def test_none(self):
        assert parse_content_signal(None) == {}

    def test_single_directive(self):
        result = parse_content_signal("ai-train=yes")
        assert result == {"ai_train": True}

    def test_whitespace_handling(self):
        result = parse_content_signal("  ai-train = yes ,  search = no  ")
        assert result == {"ai_train": True, "search": False}

    def test_no_equals(self):
        result = parse_content_signal("ai-train, search=yes")
        assert result == {"search": True}


class TestParseMarkdownTokens:
    """Tests for x-markdown-tokens header parsing."""

    def test_valid_number(self):
        assert parse_markdown_tokens("725") == 725

    def test_with_whitespace(self):
        assert parse_markdown_tokens("  3150  ") == 3150

    def test_empty(self):
        assert parse_markdown_tokens("") is None

    def test_none(self):
        assert parse_markdown_tokens(None) is None

    def test_non_numeric(self):
        assert parse_markdown_tokens("abc") is None

    def test_zero(self):
        assert parse_markdown_tokens("0") == 0


class TestIsCfMarkdownResponse:
    """Tests for Cloudflare Markdown response detection."""

    def test_text_markdown(self):
        assert is_cf_markdown_response("text/markdown; charset=utf-8") is True

    def test_text_markdown_simple(self):
        assert is_cf_markdown_response("text/markdown") is True

    def test_text_html(self):
        assert is_cf_markdown_response("text/html; charset=utf-8") is False

    def test_empty(self):
        assert is_cf_markdown_response("") is False

    def test_none(self):
        assert is_cf_markdown_response(None) is False


class TestExtractCfHeaders:
    """Tests for CF header extraction."""

    def test_all_headers_present(self):
        headers = {
            "Content-Type": "text/markdown; charset=utf-8",
            "Content-Signal": "ai-train=yes, search=yes, ai-input=yes",
            "X-Markdown-Tokens": "725",
        }
        result = extract_cf_headers(headers)
        assert result["is_cf_markdown"] is True
        assert result["markdown_tokens"] == 725
        assert result["content_signal"]["ai_train"] is True

    def test_no_cf_headers(self):
        headers = {"Content-Type": "text/html", "Server": "nginx"}
        assert extract_cf_headers(headers) == {}

    def test_case_insensitive(self):
        headers = {
            "content-signal": "ai-train=yes",
            "x-markdown-tokens": "100",
        }
        result = extract_cf_headers(headers)
        assert result["content_signal"]["ai_train"] is True
        assert result["markdown_tokens"] == 100

    def test_empty_headers(self):
        assert extract_cf_headers({}) == {}
        assert extract_cf_headers(None) == {}

    def test_partial_headers(self):
        headers = {"Content-Signal": "search=yes"}
        result = extract_cf_headers(headers)
        assert "content_signal" in result
        assert "markdown_tokens" not in result


class TestParseRfc9457Error:
    """Tests for RFC 9457 structured error parsing."""

    def test_json_format(self):
        body = '{"type": "https://cloudflare.com/errors/1020", "title": "Access Denied", "status": 1020, "detail": "Sorry, you have been blocked.", "error_category": "access_control", "retryable": false}'
        result = parse_rfc9457_error(body, "application/problem+json", 403)
        assert result is not None
        assert result["title"] == "Access Denied"
        assert result["status"] == 1020
        assert result["retryable"] is False
        assert result["error_category"] == "access_control"

    def test_json_retryable(self):
        body = '{"type": "https://cloudflare.com/errors/1015", "title": "Rate Limited", "status": 1015, "retryable": true, "retry_after": 60}'
        result = parse_rfc9457_error(body, "application/json", 429)
        assert result["retryable"] is True
        assert result["retry_after"] == 60

    def test_markdown_with_frontmatter(self):
        body = """---
type: https://cloudflare.com/errors/1020
title: Access Denied
status: 1020
error_category: access_control
retryable: false
---

# Access Denied

Sorry, you have been blocked."""
        result = parse_rfc9457_error(body, "text/markdown", 403)
        assert result is not None
        assert result["title"] == "Access Denied"
        assert result["status"] == 1020
        assert result["retryable"] is False

    def test_markdown_retryable_with_detail(self):
        body = """---
type: https://cloudflare.com/errors/1015
title: Rate Limited
status: 1015
retryable: true
retry_after: 30
---

You are being rate limited. Please wait."""
        result = parse_rfc9457_error(body, "text/markdown", 429)
        assert result["retryable"] is True
        assert result["retry_after"] == 30
        assert "rate limited" in result["detail"].lower()

    def test_not_rfc9457_html(self):
        body = "<html><body>Regular error page</body></html>"
        assert parse_rfc9457_error(body, "text/html", 403) is None

    def test_not_rfc9457_empty(self):
        assert parse_rfc9457_error("", "text/html", 500) is None
        assert parse_rfc9457_error(None, "", 0) is None

    def test_json_auto_detect(self):
        """JSON body without explicit content-type should still parse."""
        body = '{"type": "error", "status": 403, "title": "Forbidden"}'
        result = parse_rfc9457_error(body, "", 403)
        assert result is not None
        assert result["title"] == "Forbidden"

    def test_invalid_json(self):
        assert parse_rfc9457_error("{invalid json}", "application/json", 500) is None

    def test_owner_action_required(self):
        body = '{"type": "error", "status": 1000, "title": "DNS Error", "owner_action_required": true, "retryable": false}'
        result = parse_rfc9457_error(body, "application/problem+json", 500)
        assert result["owner_action_required"] is True
        assert result["retryable"] is False

    def test_ray_id_preserved(self):
        body = '{"type": "error", "status": 1020, "title": "Blocked", "ray_id": "abc123def456"}'
        result = parse_rfc9457_error(body, "application/json", 403)
        assert result["ray_id"] == "abc123def456"

    def test_markdown_no_frontmatter(self):
        """Plain markdown without frontmatter should not parse as RFC 9457."""
        body = "# Error\n\nSomething went wrong."
        assert parse_rfc9457_error(body, "text/markdown", 500) is None

    def test_frontmatter_missing_required_fields(self):
        """Frontmatter without type/status/error_category should return None."""
        body = """---
author: John
date: 2026-03-12
---

# Blog Post"""
        assert parse_rfc9457_error(body, "text/markdown", 200) is None
