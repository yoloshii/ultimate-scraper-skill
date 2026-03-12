"""ScrapeResult dataclass for standardized scraping results."""

from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime


@dataclass
class ScrapeResult:
    """Result of a scraping operation."""

    # Core result
    success: bool = False
    tier_used: int = -1
    status_code: int = 0

    # Content
    html: str = ""
    markdown: str = ""
    raw: str = ""

    # Extracted data
    extracted_data: Optional[dict] = None
    static_data: Optional[dict] = None  # __NEXT_DATA__, JSON-LD, etc.
    vision_extraction: Optional[dict] = None  # Visual LLM extraction result

    # Screenshot data
    screenshot_base64: Optional[str] = None  # Base64-encoded screenshot
    screenshot_path: Optional[str] = None    # Path to screenshot file

    # Session state
    cookies: dict = field(default_factory=dict)
    session_id: Optional[str] = None

    # Fingerprint tracking
    fingerprint_id: Optional[str] = None

    # Error info
    error: Optional[str] = None
    error_type: Optional[str] = None

    # Metadata
    url: str = ""
    final_url: str = ""  # After redirects
    content_type: str = ""
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())
    from_cache: bool = False
    metadata: dict = field(default_factory=dict)

    # Cloudflare metadata (Content-Signal, token count, RFC 9457 details)
    cf_metadata: Optional[dict] = None

    @property
    def content(self) -> str:
        """Return best available content."""
        return self.markdown or self.html or self.raw

    @property
    def formatted_output(self) -> str:
        """Return formatted output for display."""
        if self.markdown:
            return self.markdown
        elif self.html:
            return self.html[:10000] + "..." if len(self.html) > 10000 else self.html
        return self.raw

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "tier_used": self.tier_used,
            "status_code": self.status_code,
            "url": self.url,
            "final_url": self.final_url,
            "content_type": self.content_type,
            "content_length": len(self.content),
            "extracted_data": self.extracted_data,
            "static_data": self.static_data,
            "vision_extraction": self.vision_extraction,
            "screenshot_path": self.screenshot_path,
            "error": self.error,
            "error_type": self.error_type,
            "fetched_at": self.fetched_at,
            "from_cache": self.from_cache,
            "session_id": self.session_id,
            "fingerprint_id": self.fingerprint_id,
            "metadata": self.metadata,
            "cf_metadata": self.cf_metadata,
        }

    def __str__(self) -> str:
        if self.success:
            return f"ScrapeResult(success=True, tier={self.tier_used}, len={len(self.content)})"
        return f"ScrapeResult(success=False, error={self.error})"


# Custom exceptions for scraping errors
class ScrapeError(Exception):
    """Base exception for scraping errors."""
    pass


class Blocked(ScrapeError):
    """Request was blocked by anti-bot system."""
    pass


class CaptchaRequired(ScrapeError):
    """CAPTCHA challenge encountered."""
    pass


class CaptchaUnsolvable(ScrapeError):
    """Complex CAPTCHA that cannot be automatically solved."""
    pass


class PaywallDetected(ScrapeError):
    """Paywall or subscription required."""
    pass


class GeoRestricted(ScrapeError):
    """Content not available in the proxy's region."""
    pass


class RateLimited(ScrapeError):
    """Too many requests (429)."""
    pass


class SessionExpired(ScrapeError):
    """Session cookies/tokens no longer valid."""
    pass


class ProxyError(ScrapeError):
    """Proxy connection failed."""
    pass


class ContentEmpty(ScrapeError):
    """Page returned empty or minimal content."""
    pass


class StuckDetected(ScrapeError):
    """Agent stuck in action loop."""
    pass
