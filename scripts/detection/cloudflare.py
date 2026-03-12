"""Cloudflare-specific detection and parsing utilities.

Handles:
- RFC 9457 structured error responses (Markdown + YAML frontmatter, JSON)
- Content-Signal header parsing (ai-train, search, ai-input)
- Cloudflare Markdown for Agents detection
- x-markdown-tokens header parsing
"""

import json
import re
from typing import Optional


def parse_content_signal(header_value: str) -> dict:
    """
    Parse Content-Signal header into structured permissions.

    Input:  "ai-train=yes, search=yes, ai-input=yes"
    Output: {"ai_train": True, "search": True, "ai_input": True}
    """
    if not header_value:
        return {}

    result = {}
    for part in header_value.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().replace("-", "_")
        value = value.strip().lower()
        result[key] = value == "yes"
    return result


def parse_markdown_tokens(header_value: str) -> Optional[int]:
    """Parse x-markdown-tokens header into integer token count."""
    if not header_value:
        return None
    try:
        return int(header_value.strip())
    except (ValueError, TypeError):
        return None


def is_cf_markdown_response(content_type: str) -> bool:
    """Check if response Content-Type indicates Cloudflare Markdown for Agents."""
    if not content_type:
        return False
    return "text/markdown" in content_type.lower()


def extract_cf_headers(headers: dict) -> dict:
    """
    Extract Cloudflare-specific headers from response.

    Returns dict with any present CF metadata:
    - content_signal: parsed permissions dict
    - markdown_tokens: estimated token count
    - is_cf_markdown: whether response is CF markdown
    """
    if not headers:
        return {}

    # Normalize header keys to lowercase for lookup
    h = {k.lower(): v for k, v in headers.items()}

    metadata = {}

    content_signal = h.get("content-signal", "")
    if content_signal:
        metadata["content_signal"] = parse_content_signal(content_signal)

    tokens = parse_markdown_tokens(h.get("x-markdown-tokens", ""))
    if tokens is not None:
        metadata["markdown_tokens"] = tokens

    content_type = h.get("content-type", "")
    if is_cf_markdown_response(content_type):
        metadata["is_cf_markdown"] = True

    return metadata


def parse_rfc9457_error(body: str, content_type: str = "", status_code: int = 0) -> Optional[dict]:
    """
    Parse RFC 9457 structured error response from Cloudflare.

    Cloudflare serves these in two formats:
    1. Markdown with YAML frontmatter (Accept: text/markdown)
    2. JSON (Accept: application/json or application/problem+json)

    Returns parsed problem details dict or None if not an RFC 9457 response.
    Keys: type, title, status, detail, error_category, retryable, retry_after,
          owner_action_required, ray_id
    """
    if not body:
        return None

    ct = content_type.lower() if content_type else ""

    # Try JSON format first
    if "json" in ct or "problem+json" in ct:
        return _parse_rfc9457_json(body)

    # Try Markdown with YAML frontmatter
    if "markdown" in ct or body.lstrip().startswith("---"):
        return _parse_rfc9457_markdown(body)

    # For non-markdown responses, check if body looks like RFC 9457 JSON
    body_stripped = body.strip()
    if body_stripped.startswith("{") and '"type"' in body_stripped and '"status"' in body_stripped:
        return _parse_rfc9457_json(body_stripped)

    return None


def _parse_rfc9457_json(body: str) -> Optional[dict]:
    """Parse RFC 9457 JSON problem details."""
    try:
        data = json.loads(body)
        if not isinstance(data, dict):
            return None
        # Must have at least 'type' or 'status' to be RFC 9457
        if "type" not in data and "status" not in data:
            return None
        return _normalize_problem_details(data)
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_rfc9457_markdown(body: str) -> Optional[dict]:
    """Parse RFC 9457 Markdown with YAML frontmatter."""
    # Extract YAML frontmatter between --- delimiters
    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', body, re.DOTALL)
    if not match:
        return None

    frontmatter = match.group(1)
    data = {}

    # Parse YAML key-value pairs (simple flat parsing, no pyyaml dependency)
    for line in frontmatter.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        # Type conversion
        if value.lower() in ("true", "yes"):
            value = True
        elif value.lower() in ("false", "no"):
            value = False
        elif value.isdigit():
            value = int(value)

        data[key] = value

    if not data or ("type" not in data and "status" not in data and "error_category" not in data):
        return None

    # Include markdown body as 'detail' if not already set
    body_text = body[match.end():].strip()
    if body_text and "detail" not in data:
        data["detail"] = body_text[:500]

    return _normalize_problem_details(data)


def _normalize_problem_details(data: dict) -> dict:
    """Normalize RFC 9457 problem details to consistent keys."""
    return {
        "type": data.get("type", ""),
        "title": data.get("title", ""),
        "status": data.get("status", 0),
        "detail": data.get("detail", ""),
        "error_category": data.get("error_category", ""),
        "retryable": data.get("retryable", False),
        "retry_after": data.get("retry_after", data.get("retry-after", 0)),
        "owner_action_required": data.get("owner_action_required", False),
        "ray_id": data.get("ray_id", data.get("ray-id", "")),
    }
