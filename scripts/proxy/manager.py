"""Proxy management with fingerprint-aware selection and geo-targeting."""

import random
import string
from dataclasses import dataclass, field
from typing import Optional, Literal, TYPE_CHECKING
from core.config import get_config

if TYPE_CHECKING:
    from fingerprint.manager import FingerprintProfile


# Browser market share by region (2026 data)
# Used for weighted selection when no fingerprint specified
BROWSER_MARKET_SHARE = {
    "us": {"chrome": 0.65, "safari": 0.20, "edge": 0.10, "firefox": 0.05},
    "uk": {"chrome": 0.60, "safari": 0.25, "edge": 0.10, "firefox": 0.05},
    "de": {"chrome": 0.50, "firefox": 0.25, "safari": 0.15, "edge": 0.10},
    "fr": {"chrome": 0.55, "firefox": 0.20, "safari": 0.15, "edge": 0.10},
    "jp": {"chrome": 0.70, "safari": 0.15, "edge": 0.10, "firefox": 0.05},
    "cn": {"chrome": 0.60, "edge": 0.25, "firefox": 0.10, "safari": 0.05},
    "au": {"chrome": 0.60, "safari": 0.25, "edge": 0.10, "firefox": 0.05},
    "br": {"chrome": 0.75, "edge": 0.15, "firefox": 0.07, "safari": 0.03},
    "in": {"chrome": 0.80, "edge": 0.10, "firefox": 0.07, "safari": 0.03},
}

# Geo-timezone-locale correlation
GEO_PROFILES = {
    "us": {"timezone": "America/New_York", "locale": "en-US", "browsers": ["chrome", "safari", "edge"]},
    "us-ny": {"timezone": "America/New_York", "locale": "en-US", "browsers": ["chrome", "safari"]},
    "us-la": {"timezone": "America/Los_Angeles", "locale": "en-US", "browsers": ["chrome", "safari"]},
    "us-tx": {"timezone": "America/Chicago", "locale": "en-US", "browsers": ["chrome", "edge"]},
    "de": {"timezone": "Europe/Berlin", "locale": "de-DE", "browsers": ["chrome", "firefox"]},
    "de-berlin": {"timezone": "Europe/Berlin", "locale": "de-DE", "browsers": ["chrome", "firefox"]},
    "uk": {"timezone": "Europe/London", "locale": "en-GB", "browsers": ["chrome", "safari"]},
    "uk-london": {"timezone": "Europe/London", "locale": "en-GB", "browsers": ["chrome", "safari"]},
    "fr": {"timezone": "Europe/Paris", "locale": "fr-FR", "browsers": ["chrome", "firefox"]},
    "jp": {"timezone": "Asia/Tokyo", "locale": "ja-JP", "browsers": ["chrome", "edge"]},
    "cn": {"timezone": "Asia/Shanghai", "locale": "zh-CN", "browsers": ["chrome", "edge"]},
    "au": {"timezone": "Australia/Sydney", "locale": "en-AU", "browsers": ["chrome", "safari"]},
    "br": {"timezone": "America/Sao_Paulo", "locale": "pt-BR", "browsers": ["chrome", "edge"]},
    "in": {"timezone": "Asia/Kolkata", "locale": "en-IN", "browsers": ["chrome", "edge"]},
}

# Browser version ranges
BROWSER_VERSIONS = {
    "chrome": ["chrome141", "chrome142", "chrome143", "chrome144"],
    "firefox": ["firefox134", "firefox135", "firefox136"],
    "safari": ["safari17_5", "safari18"],
    "edge": ["edge139", "edge140", "edge141"],
}


@dataclass
class ProxyConfig:
    """Proxy configuration with session and geo-targeting."""

    host: str = ""
    port: int = 0
    username: str = ""
    password: str = ""
    session_id: str = ""
    geo: str = "us"
    sticky: bool = False
    proxy_type: Literal["residential", "mobile", "datacenter"] = "residential"

    # Correlated fingerprint data
    timezone: str = ""
    locale: str = ""
    browser: str = ""
    user_agent: str = ""

    @property
    def url(self) -> str:
        """Get proxy URL in format http://user:pass@host:port."""
        auth = f"{self.full_username}:{self.password}"
        return f"http://{auth}@{self.host}:{self.port}"

    @property
    def full_username(self) -> str:
        """Build full username with session and geo targeting.

        Default format: USERNAME-country-us-city-newyork-sid-ID
        Compatible with ProxyEmpire and similar providers.
        Parameters use hyphen separator, spaces in values become +
        """
        parts = [self.username]

        # Parse geo for country, region, city
        if self.geo:
            geo_parts = self.geo.split("-")
            country = geo_parts[0]
            parts.append(f"country-{country}")

            if len(geo_parts) > 1:
                # Could be region or city - treat as city for simplicity
                city = geo_parts[1].replace(" ", "+")
                parts.append(f"city-{city}")

        # Add session ID for sticky sessions
        if self.session_id:
            parts.append(f"sid-{self.session_id}")

        return "-".join(parts)

    @property
    def dict_format(self) -> dict:
        """Get proxy dict for requests/httpx."""
        return {
            "http": self.url,
            "https": self.url,
        }

    @property
    def curl_format(self) -> str:
        """Get proxy string for curl_cffi."""
        return self.url


class ProxyEmpireManager:
    """Manage residential proxies with session and geo-targeting."""

    def __init__(self):
        self.config = get_config()
        self._active_sessions: dict[str, ProxyConfig] = {}

    def get_proxy(
        self,
        geo: Optional[str] = None,
        sticky: bool = False,
        session_id: Optional[str] = None,
        proxy_type: Literal["residential", "mobile", "datacenter"] = "residential",
        fingerprint: Optional["FingerprintProfile"] = None,
    ) -> ProxyConfig:
        """
        Get a proxy configuration with optional geo-targeting and sticky session.

        Args:
            geo: Geographic target (e.g., "us", "us-ny", "de-berlin")
            sticky: Whether to use sticky session (same IP)
            session_id: Custom session ID for sticky sessions
            proxy_type: Type of proxy (residential, mobile, datacenter)
            fingerprint: Optional FingerprintProfile for consistent identity

        Returns:
            ProxyConfig with correlated fingerprint data
        """
        geo = geo or self.config.default_proxy_geo

        # Generate or use existing session ID
        if sticky and not session_id:
            session_id = self._generate_session_id()

        # Get geo profile for fingerprint correlation
        geo_key = geo.split("-")[0] if "-" in geo else geo
        profile = GEO_PROFILES.get(geo_key, GEO_PROFILES["us"])

        # Use fingerprint if provided, otherwise select based on market share
        if fingerprint:
            # Extract browser name from version (e.g., "chrome143" -> "chrome")
            browser = fingerprint.browser
            browser_version = fingerprint.browser_version
            user_agent = fingerprint.user_agent
            locale = fingerprint.accept_language.split(",")[0] if fingerprint.accept_language else profile["locale"]
        else:
            # Select browser based on regional market share (weighted)
            browser, browser_version = self._select_browser_weighted(geo_key)
            user_agent = self._get_user_agent(browser, browser_version)
            locale = profile["locale"]

        proxy_config = ProxyConfig(
            host=self.config.proxy_host,
            port=self.config.proxy_port,
            username=self.config.proxy_username,
            password=self.config.proxy_password,
            session_id=session_id or "",
            geo=geo,
            sticky=sticky,
            proxy_type=proxy_type,
            timezone=profile["timezone"],
            locale=locale,
            browser=browser_version,
            user_agent=user_agent,
        )

        # Track active sessions
        if session_id:
            self._active_sessions[session_id] = proxy_config

        return proxy_config

    def _select_browser_weighted(self, geo: str) -> tuple[str, str]:
        """Select browser based on regional market share (weighted random)."""
        shares = BROWSER_MARKET_SHARE.get(geo, BROWSER_MARKET_SHARE["us"])
        browsers = list(shares.keys())
        weights = list(shares.values())
        browser = random.choices(browsers, weights=weights, k=1)[0]
        browser_version = random.choice(BROWSER_VERSIONS[browser])
        return browser, browser_version

    def rotate_session(self, current_session_id: str, geo: Optional[str] = None) -> ProxyConfig:
        """
        Rotate to a new session while maintaining geo-targeting.

        Args:
            current_session_id: Current session to replace
            geo: Geographic target (uses current if not specified)

        Returns:
            New ProxyConfig with fresh session
        """
        # Get current geo if not specified
        if not geo and current_session_id in self._active_sessions:
            geo = self._active_sessions[current_session_id].geo

        # Remove old session
        self._active_sessions.pop(current_session_id, None)

        # Generate new session
        return self.get_proxy(geo=geo, sticky=True)

    def get_session(self, session_id: str) -> Optional[ProxyConfig]:
        """Get existing session config."""
        return self._active_sessions.get(session_id)

    def release_session(self, session_id: str) -> bool:
        """Release a sticky session."""
        if session_id in self._active_sessions:
            del self._active_sessions[session_id]
            return True
        return False

    def _generate_session_id(self) -> str:
        """Generate unique 8-character session ID."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

    def _get_user_agent(self, browser: str, version: str) -> str:
        """Get user agent string for browser version."""
        # Extract version number
        version_num = ''.join(filter(str.isdigit, version))

        user_agents = {
            "chrome": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version_num}.0.0.0 Safari/537.36",
            "firefox": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{version_num}.0) Gecko/20100101 Firefox/{version_num}.0",
            "safari": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{version_num}.0 Safari/605.1.15",
            "edge": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version_num}.0.0.0 Safari/537.36 Edg/{version_num}.0.0.0",
        }

        return user_agents.get(browser, user_agents["chrome"])

    @property
    def is_configured(self) -> bool:
        """Check if proxy credentials are configured."""
        return self.config.proxy_configured

    def get_correlated_headers(self, proxy_config: ProxyConfig) -> dict:
        """
        Get HTTP headers correlated with proxy geo/fingerprint.

        Args:
            proxy_config: Proxy configuration with geo/browser info

        Returns:
            Headers dict matching proxy fingerprint
        """
        return {
            "User-Agent": proxy_config.user_agent,
            "Accept-Language": f"{proxy_config.locale},{proxy_config.locale.split('-')[0]};q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
