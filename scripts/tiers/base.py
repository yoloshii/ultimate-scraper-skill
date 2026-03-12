"""Base class for all scraping tiers."""

from abc import ABC, abstractmethod
from typing import Optional
from core.result import ScrapeResult
from proxy.manager import ProxyConfig


class BaseTier(ABC):
    """Abstract base class for scraping tiers."""

    TIER_NUMBER: int = -1
    TIER_NAME: str = "base"

    @abstractmethod
    async def fetch(
        self,
        url: str,
        proxy: Optional[ProxyConfig] = None,
        headers: Optional[dict] = None,
        timeout: int = 30,
        **kwargs,
    ) -> ScrapeResult:
        """
        Fetch content from URL.

        Args:
            url: Target URL
            proxy: Optional proxy configuration
            headers: Optional custom headers
            timeout: Request timeout in seconds
            **kwargs: Tier-specific options

        Returns:
            ScrapeResult with fetched content
        """
        pass

    def can_handle(self, url: str, profile: Optional["ScrapeProfile"] = None) -> bool:
        """
        Check if this tier can handle the given URL/profile.

        Args:
            url: Target URL
            profile: Optional site profile with anti-bot info

        Returns:
            True if this tier is suitable
        """
        return True

    @property
    def tier_info(self) -> dict:
        """Get tier metadata."""
        return {
            "tier": self.TIER_NUMBER,
            "name": self.TIER_NAME,
        }


class TierError(Exception):
    """Base exception for tier-specific errors."""

    def __init__(self, message: str, tier: int = -1, recoverable: bool = True):
        self.tier = tier
        self.recoverable = recoverable
        super().__init__(message)


class TierBlocked(TierError):
    """Request blocked by anti-bot system."""
    pass


class TierTimeout(TierError):
    """Request timed out."""
    pass


class TierCaptcha(TierError):
    """CAPTCHA challenge encountered."""
    pass
