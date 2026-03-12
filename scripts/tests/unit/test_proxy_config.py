"""Unit tests for ProxyConfig and ProxyEmpireManager."""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


class TestProxyConfig:
    """Tests for ProxyConfig dataclass."""

    @pytest.fixture
    def proxy_config(self, mock_config):
        """Create a ProxyConfig with test values."""
        from proxy.manager import ProxyConfig
        return ProxyConfig(
            host="proxy.example.com",
            port=8080,
            username="testuser",
            password="testpass",
            session_id="abc123",
            geo="us-ny",
            sticky=True,
            timezone="America/New_York",
            locale="en-US",
            user_agent="Mozilla/5.0 Test",
        )

    def test_proxy_config_url_format(self, proxy_config):
        """ProxyConfig.url generates correct format."""
        url = proxy_config.url

        assert "proxy.example.com:8080" in url
        assert "testpass" in url
        assert url.startswith("http://")

    def test_proxy_config_full_username(self, proxy_config):
        """full_username includes geo and session."""
        full = proxy_config.full_username

        assert "testuser" in full
        assert "country-us" in full
        assert "city-ny" in full
        assert "sid-abc123" in full

    def test_proxy_config_full_username_no_session(self, mock_config):
        """full_username works without session ID."""
        from proxy.manager import ProxyConfig
        config = ProxyConfig(
            username="user",
            password="pass",
            geo="de",
            session_id="",
        )
        full = config.full_username

        assert "user" in full
        assert "country-de" in full
        assert "sid-" not in full

    def test_proxy_config_dict_format(self, proxy_config):
        """dict_format returns httpx-compatible dict."""
        d = proxy_config.dict_format

        assert "http" in d
        assert "https" in d
        assert d["http"] == proxy_config.url
        assert d["https"] == proxy_config.url

    def test_proxy_config_curl_format(self, proxy_config):
        """curl_format returns curl_cffi-compatible string."""
        curl = proxy_config.curl_format

        assert curl == proxy_config.url


class TestProxyEmpireManager:
    """Tests for ProxyEmpireManager."""

    @pytest.fixture
    def manager(self, mock_config, monkeypatch):
        """Create ProxyEmpireManager with mock config."""
        from core.config import ScraperConfig
        from core import config as config_module

        # Create mock config with proxy credentials
        mock_cfg = ScraperConfig(
            proxy_username="test_user",
            proxy_password="test_pass",
            proxy_host="test-proxy.example.com",
            proxy_port=5000,
            default_proxy_geo="us",
        )

        # Override global config
        config_module._config = mock_cfg

        from proxy.manager import ProxyEmpireManager
        return ProxyEmpireManager()

    def test_generate_session_id_format(self, manager):
        """Session ID has correct format and uniqueness."""
        session_id = manager._generate_session_id()

        assert len(session_id) == 8
        assert session_id.isalnum()
        assert session_id.islower() or any(c.isdigit() for c in session_id)

    def test_generate_session_id_unique(self, manager):
        """Multiple session IDs are unique."""
        ids = [manager._generate_session_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_get_proxy_basic(self, manager):
        """get_proxy returns valid ProxyConfig."""
        config = manager.get_proxy(geo="us")

        assert config.geo == "us"
        assert config.host == "test-proxy.example.com"
        assert config.port == 5000

    def test_get_proxy_sticky_session(self, manager):
        """get_proxy with sticky=True creates session."""
        config = manager.get_proxy(geo="de", sticky=True)

        assert config.sticky is True
        assert config.session_id != ""
        assert len(config.session_id) == 8

    def test_get_proxy_custom_session_id(self, manager):
        """get_proxy with custom session_id uses it."""
        config = manager.get_proxy(geo="uk", sticky=True, session_id="custom123")

        assert config.session_id == "custom123"

    def test_get_proxy_geo_correlation(self, manager):
        """Proxy config includes correlated timezone/locale."""
        config = manager.get_proxy(geo="jp")

        assert config.timezone == "Asia/Tokyo"
        assert config.locale == "ja-JP"

    def test_get_proxy_with_fingerprint(self, manager, mock_config, monkeypatch):
        """get_proxy uses fingerprint data when provided."""
        # Create a mock fingerprint
        from fingerprint.manager import FingerprintProfile

        fp = FingerprintProfile(
            fingerprint_id="test123",
            domain="example.com",
            browser="firefox",
            browser_version="firefox135",
            impersonate="firefox135",
            user_agent="Mozilla/5.0 Firefox Custom UA",
            accept_language="fr-FR,fr;q=0.9",
            platform="Linux x86_64",
            geo="fr",
        )

        config = manager.get_proxy(geo="fr", fingerprint=fp)

        assert config.user_agent == "Mozilla/5.0 Firefox Custom UA"
        assert "fr-FR" in config.locale

    def test_select_browser_weighted_returns_valid(self, manager):
        """_select_browser_weighted returns valid browser."""
        for _ in range(100):
            browser, version = manager._select_browser_weighted("us")
            assert browser in ["chrome", "safari", "edge", "firefox"]
            assert browser in version

    def test_get_correlated_headers(self, manager):
        """get_correlated_headers returns proper headers dict."""
        config = manager.get_proxy(geo="us")
        headers = manager.get_correlated_headers(config)

        assert "User-Agent" in headers
        assert "Accept-Language" in headers
        assert "Accept" in headers
        assert "Accept-Encoding" in headers

    def test_get_correlated_headers_match_proxy(self, manager):
        """Headers match proxy configuration."""
        config = manager.get_proxy(geo="de")
        headers = manager.get_correlated_headers(config)

        # User-Agent should match
        assert headers["User-Agent"] == config.user_agent

        # Accept-Language should include German
        assert "de" in headers["Accept-Language"].lower()

    def test_rotate_session(self, manager):
        """rotate_session creates new session."""
        original = manager.get_proxy(geo="uk", sticky=True)
        original_id = original.session_id

        rotated = manager.rotate_session(original_id, geo="uk")

        assert rotated.session_id != original_id
        assert rotated.geo == "uk"

    def test_get_session(self, manager):
        """get_session retrieves active session."""
        config = manager.get_proxy(geo="au", sticky=True)
        session_id = config.session_id

        retrieved = manager.get_session(session_id)

        assert retrieved is not None
        assert retrieved.session_id == session_id

    def test_release_session(self, manager):
        """release_session removes session from tracking."""
        config = manager.get_proxy(geo="br", sticky=True)
        session_id = config.session_id

        result = manager.release_session(session_id)
        assert result is True

        # Should not be findable anymore
        retrieved = manager.get_session(session_id)
        assert retrieved is None

    def test_release_session_nonexistent(self, manager):
        """release_session returns False for unknown session."""
        result = manager.release_session("nonexistent_session")
        assert result is False

    def test_is_configured(self, manager):
        """is_configured returns True when credentials set."""
        assert manager.is_configured is True

    def test_get_user_agent_chrome(self, manager):
        """_get_user_agent generates Chrome UA correctly."""
        ua = manager._get_user_agent("chrome", "chrome143")

        assert "Chrome/143" in ua
        assert "Windows NT" in ua

    def test_get_user_agent_firefox(self, manager):
        """_get_user_agent generates Firefox UA correctly."""
        ua = manager._get_user_agent("firefox", "firefox135")

        assert "Firefox/135" in ua
        assert "Gecko" in ua

    def test_get_user_agent_safari(self, manager):
        """_get_user_agent generates Safari UA correctly."""
        ua = manager._get_user_agent("safari", "safari18")

        assert "Safari" in ua
        assert "Version/18" in ua
        assert "Macintosh" in ua

    def test_get_user_agent_edge(self, manager):
        """_get_user_agent generates Edge UA correctly."""
        ua = manager._get_user_agent("edge", "edge140")

        assert "Edg/140" in ua
        assert "Windows NT" in ua
