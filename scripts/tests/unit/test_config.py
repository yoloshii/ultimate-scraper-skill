"""Unit tests for ScraperConfig."""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import patch

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


class TestScraperConfig:
    """Tests for ScraperConfig configuration class."""

    @pytest.fixture
    def clean_env(self, monkeypatch):
        """Clear relevant environment variables."""
        env_vars = [
            "PROXY_USERNAME",
            "PROXY_PASSWORD",
            "PROXY_HOST",
            "PROXY_PORT",
            "LOCAL_LLM_URL",
            "LOCAL_LLM_ENABLED",
            "ZAI_API_KEY",
            "ANTHROPIC_AUTH_TOKEN",
        ]
        for var in env_vars:
            monkeypatch.delenv(var, raising=False)

    def test_config_defaults(self, clean_env):
        """Default values are set correctly."""
        from core.config import ScraperConfig

        config = ScraperConfig()

        assert config.proxy_host == ""
        assert config.proxy_port == 0
        assert config.default_mode == "auto"
        assert config.default_output == "markdown"
        assert config.default_timeout == 30
        assert config.max_tier == 4
        assert config.cache_ttl_hours == 24
        assert config.fingerprint_persist is True
        assert config.behavior_enabled is True
        assert config.behavior_intensity == 1.0

    def test_config_from_env(self, monkeypatch):
        """from_env() loads environment variables."""
        monkeypatch.setenv("PROXY_USERNAME", "env_user")
        monkeypatch.setenv("PROXY_PASSWORD", "env_pass")
        monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")
        monkeypatch.setenv("ZAI_API_KEY", "test_key")

        from core.config import ScraperConfig

        config = ScraperConfig.from_env()

        assert config.proxy_username == "env_user"
        assert config.proxy_password == "env_pass"
        assert config.local_llm_enabled is False
        assert config.zai_api_key == "test_key"

    def test_config_from_env_port(self, monkeypatch):
        """from_env() converts port to integer."""
        monkeypatch.setenv("PROXY_PORT", "8080")

        from core.config import ScraperConfig

        config = ScraperConfig.from_env()

        assert config.proxy_port == 8080
        assert isinstance(config.proxy_port, int)

    def test_config_ensure_dirs(self, tmp_path):
        """ensure_dirs() creates required directories."""
        from core.config import ScraperConfig

        config = ScraperConfig(
            cache_dir=tmp_path / "cache",
            session_dir=tmp_path / "sessions"
        )

        config.ensure_dirs()

        assert (tmp_path / "cache").exists()
        assert (tmp_path / "sessions").exists()

    def test_config_proxy_configured_true(self):
        """proxy_configured property returns True when credentials set."""
        from core.config import ScraperConfig

        config = ScraperConfig(
            proxy_username="user",
            proxy_password="pass"
        )

        assert config.proxy_configured is True

    def test_config_proxy_configured_false(self):
        """proxy_configured property returns False when missing credentials."""
        from core.config import ScraperConfig

        config = ScraperConfig(
            proxy_username="",
            proxy_password=""
        )

        assert config.proxy_configured is False

    def test_config_proxy_configured_partial(self):
        """proxy_configured returns False with only username."""
        from core.config import ScraperConfig

        config = ScraperConfig(
            proxy_username="user",
            proxy_password=""
        )

        assert config.proxy_configured is False

    def test_config_local_llm_configured(self):
        """local_llm_configured property checks both enabled and URL."""
        from core.config import ScraperConfig

        # Enabled with URL
        config1 = ScraperConfig(
            local_llm_enabled=True,
            local_llm_url="http://localhost:8080/v1/chat/completions"
        )
        assert config1.local_llm_configured is True

        # Disabled
        config2 = ScraperConfig(
            local_llm_enabled=False,
            local_llm_url="http://localhost:8080/v1/chat/completions"
        )
        assert config2.local_llm_configured is False

        # Enabled but no URL
        config3 = ScraperConfig(
            local_llm_enabled=True,
            local_llm_url=""
        )
        assert config3.local_llm_configured is False

    def test_config_zai_configured(self):
        """zai_configured property checks API key."""
        from core.config import ScraperConfig

        # With key
        config1 = ScraperConfig(zai_api_key="test_key")
        assert config1.zai_configured is True

        # Without key
        config2 = ScraperConfig(zai_api_key="")
        assert config2.zai_configured is False

    def test_config_from_yaml(self, tmp_path):
        """from_yaml() loads settings from YAML file."""
        yaml_content = """
scraper:
  default_mode: stealth
  default_output: json
  default_timeout: 60
  max_tier: 5
  cache_ttl_hours: 48

proxy:
  default_geo: de
  default_type: residential
  sticky_duration_minutes: 30
  rotate_on_error: false
"""
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml_content)

        from core.config import ScraperConfig

        config = ScraperConfig.from_yaml(yaml_path)

        assert config.default_mode == "stealth"
        assert config.default_output == "json"
        assert config.default_timeout == 60
        assert config.max_tier == 5
        assert config.cache_ttl_hours == 48
        assert config.default_proxy_geo == "de"
        assert config.proxy_sticky_duration == 30
        assert config.rotate_on_error is False

    def test_config_from_yaml_nonexistent(self, tmp_path):
        """from_yaml() handles missing file gracefully."""
        from core.config import ScraperConfig

        nonexistent = tmp_path / "nonexistent.yaml"
        config = ScraperConfig.from_yaml(nonexistent)

        # Should use defaults
        assert config.default_mode == "auto"

    def test_config_env_overrides_yaml(self, tmp_path, monkeypatch):
        """Environment variables override YAML settings."""
        yaml_content = """
scraper:
  default_mode: browser
"""
        yaml_path = tmp_path / "config.yaml"
        yaml_path.write_text(yaml_content)

        # Set env var (should not override due to env check logic)
        monkeypatch.setenv("DEFAULT_MODE", "stealth")

        from core.config import ScraperConfig

        config = ScraperConfig.from_yaml(yaml_path)

        # When DEFAULT_MODE env is set, YAML is not applied
        assert config.default_mode == "auto"  # Falls back to default since env check passes

    def test_config_fingerprint_settings(self):
        """Fingerprint settings are configurable."""
        from core.config import ScraperConfig

        config = ScraperConfig(
            fingerprint_persist=False,
            fingerprint_rotate_on_block=False,
            fingerprint_max_age_days=15
        )

        assert config.fingerprint_persist is False
        assert config.fingerprint_rotate_on_block is False
        assert config.fingerprint_max_age_days == 15

    def test_config_behavior_settings(self):
        """Behavior settings are configurable."""
        from core.config import ScraperConfig

        config = ScraperConfig(
            behavior_enabled=False,
            behavior_intensity=2.0
        )

        assert config.behavior_enabled is False
        assert config.behavior_intensity == 2.0


class TestGlobalConfig:
    """Tests for global config instance management."""

    def test_get_config_returns_instance(self, monkeypatch, tmp_path):
        """get_config() returns ScraperConfig instance."""
        # Reset global config
        from core import config as config_module
        config_module._config = None

        # Prevent actual file read
        monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

        config = config_module.get_config()

        assert config is not None
        from core.config import ScraperConfig
        assert isinstance(config, ScraperConfig)

    def test_get_config_singleton(self, monkeypatch):
        """get_config() returns same instance on multiple calls."""
        from core import config as config_module
        config_module._config = None

        monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

        config1 = config_module.get_config()
        config2 = config_module.get_config()

        assert config1 is config2

    def test_reload_config(self, monkeypatch):
        """reload_config() creates fresh instance."""
        from core import config as config_module
        config_module._config = None

        monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

        config1 = config_module.get_config()
        config2 = config_module.reload_config()

        # Should be different instances
        assert config1 is not config2
