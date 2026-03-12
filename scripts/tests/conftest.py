"""Shared fixtures for ultimate-scraper test suite."""

import pytest
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary SQLite database path."""
    return tmp_path / "test_sessions.db"


@pytest.fixture
def temp_cache_db(tmp_path):
    """Create temporary cache database path."""
    return tmp_path / "test_cache.db"


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir


@pytest.fixture
def temp_session_dir(tmp_path):
    """Create temporary session directory."""
    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    return session_dir


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("PROXY_USERNAME", "test_user")
    monkeypatch.setenv("PROXY_PASSWORD", "test_pass")
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")
    monkeypatch.setenv("ZAI_API_KEY", "")


@pytest.fixture
def mock_config(tmp_path, monkeypatch):
    """Create mock config with temp paths."""
    # Set env to disable external services
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

    # Import after setting env
    from core.config import ScraperConfig

    config = ScraperConfig(
        cache_dir=tmp_path / "cache",
        session_dir=tmp_path / "sessions",
        proxy_username="test_user",
        proxy_password="test_pass",
        local_llm_enabled=False,
    )
    config.ensure_dirs()
    return config


@pytest.fixture
def fingerprint_manager(temp_db, monkeypatch):
    """FingerprintManager with temp database."""
    # Mock get_config to return a config with our temp path
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

    from fingerprint.manager import FingerprintManager
    from core.config import ScraperConfig
    from core import config as config_module

    # Create mock config
    mock_cfg = ScraperConfig(cache_dir=temp_db.parent)
    mock_cfg.ensure_dirs()

    # Override global config
    config_module._config = mock_cfg

    return FingerprintManager(db_path=temp_db)


@pytest.fixture
def session_manager(temp_db, tmp_path, monkeypatch):
    """SessionManager with temp database."""
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

    from session.manager import SessionManager
    from core.config import ScraperConfig
    from core import config as config_module

    # Create mock config
    mock_cfg = ScraperConfig(
        cache_dir=temp_db.parent,
        session_dir=tmp_path / "sessions"
    )
    mock_cfg.ensure_dirs()

    # Override global config
    config_module._config = mock_cfg

    return SessionManager(db_path=temp_db)


@pytest.fixture
def cache_manager(temp_cache_db, monkeypatch):
    """CacheManager with temp database."""
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "false")

    from cache.manager import CacheManager
    from core.config import ScraperConfig
    from core import config as config_module

    # Create mock config
    mock_cfg = ScraperConfig(cache_dir=temp_cache_db.parent)
    mock_cfg.ensure_dirs()

    # Override global config
    config_module._config = mock_cfg

    return CacheManager(db_path=temp_cache_db)


@pytest.fixture
def sample_html_nextjs():
    """Sample HTML with Next.js __NEXT_DATA__."""
    return '''
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"title":"Test","items":[1,2,3]}},"page":"/test"}
</script>
<div id="__next">Content here</div>
</body>
</html>
'''


@pytest.fixture
def sample_html_nuxt():
    """Sample HTML with Nuxt __NUXT__."""
    return '''
<!DOCTYPE html>
<html>
<head><title>Nuxt Page</title></head>
<body>
<div id="__nuxt">Content</div>
<script>window.__NUXT__={"data":{"items":["a","b","c"]},"state":{}};</script>
</body>
</html>
'''


@pytest.fixture
def sample_html_json_ld():
    """Sample HTML with JSON-LD structured data."""
    return '''
<!DOCTYPE html>
<html>
<head>
<title>Product Page</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Widget","price":"19.99"}
</script>
</head>
<body><h1>Widget</h1></body>
</html>
'''


@pytest.fixture
def sample_html_cloudflare():
    """Sample HTML with Cloudflare challenge."""
    return '''
<!DOCTYPE html>
<html>
<head><title>Just a moment...</title></head>
<body>
<div class="cf-browser-verification">
Checking your browser before accessing the site.
</div>
<script src="/cdn-cgi/challenge-platform/script.js"></script>
</body>
</html>
'''


@pytest.fixture
def sample_html_paywall():
    """Sample HTML with paywall indicators."""
    return '''
<!DOCTYPE html>
<html>
<head><title>Premium Article</title></head>
<body>
<h1>Exclusive Article</h1>
<p>This is the preview...</p>
<div class="paywall-modal">
<h2>Subscribe to continue reading</h2>
<p>You've reached your free article limit.</p>
</div>
</body>
</html>
'''


@pytest.fixture
def sample_html_captcha():
    """Sample HTML with CAPTCHA."""
    return '''
<!DOCTYPE html>
<html>
<head><title>Verification</title></head>
<body>
<h1>Please verify you are human</h1>
<div class="g-recaptcha" data-sitekey="abc123"></div>
<script src="https://www.google.com/recaptcha/api.js"></script>
</body>
</html>
'''


@pytest.fixture
def sample_html_minimal():
    """Sample HTML with minimal content (potential block)."""
    return '''
<!DOCTYPE html>
<html>
<head><title></title></head>
<body></body>
</html>
'''


@pytest.fixture
def sample_html_apollo():
    """Sample HTML with Apollo GraphQL state."""
    return '''
<!DOCTYPE html>
<html>
<head><title>Apollo App</title></head>
<body>
<div id="root"></div>
<script>window.__APOLLO_STATE__={"ROOT_QUERY":{"items":[{"id":"1","name":"Test"}]}};</script>
</body>
</html>
'''


# Markers for test categorization
def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests (requires network)")
    config.addinivalue_line("markers", "slow: slow tests (>10 seconds)")
    config.addinivalue_line("markers", "integration: integration tests (SQLite only)")
    config.addinivalue_line("markers", "unit: unit tests (no external dependencies)")
