"""ScraperConfig for centralized configuration management."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import yaml


@dataclass
class ScraperConfig:
    """Centralized configuration for the scraper."""

    # Proxy settings (bring your own — any HTTP/SOCKS5 provider)
    proxy_username: str = ""
    proxy_password: str = ""
    proxy_host: str = ""
    proxy_port: int = 0

    # LLM routing - Local (PRIMARY, any OpenAI-compatible API)
    local_llm_url: str = ""
    local_llm_enabled: bool = False

    # LLM routing - z.ai (FALLBACK 1)
    zai_api_key: str = ""
    zai_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    zai_timeout_ms: int = 600000

    # LLM routing - Anthropic (FALLBACK 2)
    anthropic_max_url: str = "https://api.anthropic.com"

    # Paths
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "ultimate-scraper")
    session_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "ultimate-scraper" / "sessions")
    skill_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent.parent.resolve())

    # Scraper defaults
    default_mode: str = "auto"
    default_output: str = "markdown"
    default_timeout: int = 30
    max_tier: int = 4
    cache_ttl_hours: int = 24

    # Proxy defaults
    default_proxy_geo: str = "us"
    default_proxy_type: str = "residential"
    proxy_sticky_duration: int = 10  # minutes
    rotate_on_error: bool = True

    # Retry settings
    max_retries: int = 3
    retry_backoff_base: int = 2

    # Fingerprint persistence settings
    fingerprint_persist: bool = True           # Enable fingerprint persistence per domain
    fingerprint_rotate_on_block: bool = True   # Auto-rotate fingerprint when blocked
    fingerprint_max_age_days: int = 30         # Max age before rotating fingerprint

    # Behavioral simulation settings
    behavior_enabled: bool = True              # Enable human-like behavior simulation
    behavior_intensity: float = 1.0            # Intensity (0.5=fast, 1.0=normal, 2.0=slow)

    # Rate limiting (E3)
    rate_limits: dict = field(default_factory=lambda: {
        "default": 8, "linkedin.com": 4, "facebook.com": 5,
        "twitter.com": 6, "x.com": 6, "instagram.com": 4,
    })
    rate_limiting_enabled: bool = True

    # CAPTCHA solving (E1)
    capsolver_api_key: str = ""
    twocaptcha_api_key: str = ""

    # CloakBrowser (E2) — "auto" detects availability, "1" forces, "0" disables
    cloakbrowser_enabled: str = "auto"

    # Tracker blocking (E8)
    block_trackers: bool = True

    # WebMCP (E5) — "auto" detects Chrome 147+, "1" forces, "0" disables
    webmcp_enabled: str = "auto"
    chrome_channel: str = ""  # chrome-dev, chrome-beta, chrome-canary, or empty

    @classmethod
    def from_env(cls) -> "ScraperConfig":
        """Load configuration from environment variables."""
        config = cls()

        # Proxy (any provider)
        config.proxy_username = os.environ.get("PROXY_USERNAME", "")
        config.proxy_password = os.environ.get("PROXY_PASSWORD", "")
        config.proxy_host = os.environ.get("PROXY_HOST", config.proxy_host)
        config.proxy_port = int(os.environ.get("PROXY_PORT", str(config.proxy_port)) or "0")

        # Local LLM
        config.local_llm_url = os.environ.get("LOCAL_LLM_URL", config.local_llm_url)
        config.local_llm_enabled = os.environ.get("LOCAL_LLM_ENABLED", "true").lower() == "true"

        # z.ai
        config.zai_api_key = os.environ.get("ZAI_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
        config.zai_base_url = os.environ.get("ZAI_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL", config.zai_base_url)
        config.zai_timeout_ms = int(os.environ.get("ZAI_TIMEOUT_MS") or os.environ.get("API_TIMEOUT_MS", config.zai_timeout_ms))

        # Anthropic
        config.anthropic_max_url = os.environ.get("ANTHROPIC_BASE_URL", config.anthropic_max_url)

        # CAPTCHA solving
        config.capsolver_api_key = os.environ.get("CAPSOLVER_API_KEY", "")
        config.twocaptcha_api_key = os.environ.get("TWOCAPTCHA_API_KEY", "")

        # CloakBrowser
        config.cloakbrowser_enabled = os.environ.get("CLOAKBROWSER_ENABLED", "auto")

        # WebMCP
        config.webmcp_enabled = os.environ.get("WEBMCP_ENABLED", "auto")
        config.chrome_channel = os.environ.get("CHROME_CHANNEL", "")

        return config

    @classmethod
    def from_yaml(cls, path: Path) -> "ScraperConfig":
        """Load configuration from YAML file, with env var overrides."""
        config = cls.from_env()

        if path.exists():
            with open(path) as f:
                data = yaml.safe_load(f) or {}

            # Apply YAML settings (env vars take precedence)
            if "scraper" in data:
                scraper = data["scraper"]
                if not os.environ.get("DEFAULT_MODE"):
                    config.default_mode = scraper.get("default_mode", config.default_mode)
                if not os.environ.get("DEFAULT_OUTPUT"):
                    config.default_output = scraper.get("default_output", config.default_output)
                config.default_timeout = scraper.get("default_timeout", config.default_timeout)
                config.max_tier = scraper.get("max_tier", config.max_tier)
                config.cache_ttl_hours = scraper.get("cache_ttl_hours", config.cache_ttl_hours)

            if "proxy" in data:
                proxy = data["proxy"]
                config.default_proxy_geo = proxy.get("default_geo", config.default_proxy_geo)
                config.default_proxy_type = proxy.get("default_type", config.default_proxy_type)
                config.proxy_sticky_duration = proxy.get("sticky_duration_minutes", config.proxy_sticky_duration)
                config.rotate_on_error = proxy.get("rotate_on_error", config.rotate_on_error)

            # CAPTCHA solving (E1) — env vars take precedence
            if "captcha" in data:
                cap = data["captcha"]
                if not os.environ.get("CAPSOLVER_API_KEY"):
                    config.capsolver_api_key = cap.get("capsolver_api_key", config.capsolver_api_key)
                if not os.environ.get("TWOCAPTCHA_API_KEY"):
                    config.twocaptcha_api_key = cap.get("twocaptcha_api_key", config.twocaptcha_api_key)

            # CloakBrowser (E2) — env var takes precedence
            if "cloakbrowser" in data:
                cb = data["cloakbrowser"]
                if not os.environ.get("CLOAKBROWSER_ENABLED"):
                    config.cloakbrowser_enabled = str(cb.get("enabled", config.cloakbrowser_enabled))

            # Rate limiting (E3)
            if "rate_limiting" in data:
                rl = data["rate_limiting"]
                config.rate_limiting_enabled = rl.get("enabled", config.rate_limiting_enabled)
                if "limits" in rl:
                    config.rate_limits.update(rl["limits"])

            # WebMCP (E5) — env var takes precedence
            if "webmcp" in data:
                wm = data["webmcp"]
                if not os.environ.get("WEBMCP_ENABLED"):
                    config.webmcp_enabled = str(wm.get("enabled", config.webmcp_enabled))
                if not os.environ.get("CHROME_CHANNEL"):
                    config.chrome_channel = wm.get("chrome_channel", config.chrome_channel)

            # Tracker blocking (E8)
            if "tracker_blocking" in data:
                tb = data["tracker_blocking"]
                config.block_trackers = tb.get("enabled", config.block_trackers)

        return config

    def ensure_dirs(self) -> None:
        """Ensure all required directories exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session_dir.mkdir(parents=True, exist_ok=True)

    @property
    def proxy_configured(self) -> bool:
        """Check if proxy credentials are configured."""
        return bool(self.proxy_username and self.proxy_password)

    @property
    def local_llm_configured(self) -> bool:
        """Check if local LLM is configured."""
        return self.local_llm_enabled and bool(self.local_llm_url)

    @property
    def zai_configured(self) -> bool:
        """Check if z.ai is configured."""
        return bool(self.zai_api_key)

    @property
    def captcha_solver_configured(self) -> bool:
        """Check if any CAPTCHA solver is configured."""
        return bool(self.capsolver_api_key or self.twocaptcha_api_key)


# Global config instance
_config: Optional[ScraperConfig] = None


def get_config() -> ScraperConfig:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        config_path = Path(__file__).parent.parent.parent / "config" / "default.yaml"
        _config = ScraperConfig.from_yaml(config_path)
        _config.ensure_dirs()
    return _config


def reload_config() -> ScraperConfig:
    """Force reload of configuration."""
    global _config
    _config = None
    return get_config()
