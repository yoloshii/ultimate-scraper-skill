"""Integration tests for session lifecycle management."""

import pytest
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.integration
class TestSessionLifecycle:
    """Integration tests for session persistence."""

    def test_session_create_and_load(self, session_manager):
        """Create session, load returns same data."""
        # Create session
        session = session_manager.create(
            session_id="test-session-1",
            url="https://example.com",
            proxy_geo="us"
        )

        # Load should return same data
        loaded = session_manager.get("test-session-1")

        assert loaded is not None
        assert loaded.session_id == "test-session-1"
        assert loaded.url == "https://example.com"
        assert loaded.proxy_geo == "us"

    def test_session_with_fingerprint_id(self, session_manager):
        """Session stores and retrieves fingerprint_id."""
        from session.manager import SessionState

        session = SessionState(
            session_id="fp-session-test",
            fingerprint_id="fp-12345"
        )
        session_manager.save(session)

        loaded = session_manager.get("fp-session-test")

        assert loaded is not None
        assert loaded.fingerprint_id == "fp-12345"

    def test_session_update_cookies(self, session_manager):
        """update_cookies() merges cookie data."""
        session = session_manager.create(
            session_id="cookie-test",
            url="https://example.com"
        )

        # Add initial cookies
        session_manager.update_cookies("cookie-test", {"session": "abc123"})

        # Add more cookies
        session_manager.update_cookies("cookie-test", {"token": "xyz789"})

        # Load and verify merged
        loaded = session_manager.get("cookie-test")

        assert loaded.cookies.get("session") == "abc123"
        assert loaded.cookies.get("token") == "xyz789"

    def test_session_cleanup_expired(self, session_manager, temp_db, tmp_path, monkeypatch):
        """cleanup_expired() removes old sessions."""
        from session.manager import SessionManager

        # Create manager with very short TTL
        short_ttl_manager = SessionManager(db_path=temp_db, max_age_hours=0)

        # Create session (will expire immediately)
        short_ttl_manager.create("expired-session", url="https://example.com")

        # Wait a moment
        import time
        time.sleep(0.1)

        # Cleanup
        deleted = short_ttl_manager.cleanup_expired()

        # Session should be gone
        loaded = short_ttl_manager.get("expired-session")
        assert loaded is None

    def test_session_get_or_create_existing(self, session_manager):
        """get_or_create returns existing session."""
        session1 = session_manager.create("existing-session", url="https://site.com")
        session1_created = session1.created_at

        session2 = session_manager.get_or_create("existing-session", url="https://other.com")

        # Should return same session
        assert session2.created_at == session1_created
        assert session2.url == "https://site.com"  # Original URL

    def test_session_get_or_create_new(self, session_manager):
        """get_or_create creates new session when not exists."""
        session = session_manager.get_or_create("new-session", url="https://new-site.com")

        assert session.session_id == "new-session"
        assert session.url == "https://new-site.com"

    def test_session_delete(self, session_manager):
        """delete() removes session from database."""
        session_manager.create("to-delete", url="https://example.com")

        result = session_manager.delete("to-delete")

        assert result is True

        loaded = session_manager.get("to-delete")
        assert loaded is None

    def test_session_delete_nonexistent(self, session_manager):
        """delete() returns False for nonexistent session."""
        result = session_manager.delete("nonexistent-session")
        assert result is False

    def test_session_list_sessions(self, session_manager):
        """list_sessions() returns active sessions."""
        session_manager.create("list-test-1", url="https://site1.com", proxy_geo="us")
        session_manager.create("list-test-2", url="https://site2.com", proxy_geo="de")

        sessions = session_manager.list_sessions()

        # Should include our sessions
        session_ids = [s["session_id"] for s in sessions]
        assert "list-test-1" in session_ids
        assert "list-test-2" in session_ids

    def test_session_with_local_storage(self, session_manager):
        """Session stores and retrieves local storage."""
        from session.manager import SessionState

        session = SessionState(
            session_id="storage-test",
            local_storage={
                "https://example.com": {"key1": "value1", "key2": "value2"}
            }
        )
        session_manager.save(session)

        loaded = session_manager.get("storage-test")

        assert "https://example.com" in loaded.local_storage
        assert loaded.local_storage["https://example.com"]["key1"] == "value1"

    def test_session_with_ref_map(self, session_manager):
        """Session stores and retrieves element ref map."""
        from session.manager import SessionState

        session = SessionState(
            session_id="ref-test",
            ref_map={"@e1": {"selector": "#button", "type": "button"}}
        )
        session_manager.save(session)

        loaded = session_manager.get("ref-test")

        assert "@e1" in loaded.ref_map

    def test_session_touch_updates_timestamp(self, session_manager):
        """Session touch() updates updated_at."""
        session = session_manager.create("touch-test", url="https://example.com")
        original_updated = session.updated_at

        import time
        time.sleep(0.01)

        session.touch()
        session_manager.save(session)

        loaded = session_manager.get("touch-test")
        assert loaded.updated_at != original_updated

    def test_session_storage_state_path(self, session_manager, tmp_path):
        """get_storage_state_path returns correct path."""
        path = session_manager.get_storage_state_path("state-test")

        assert "state-test" in str(path)
        assert str(path).endswith("_storage.json")

    def test_session_save_and_load_storage_state(self, session_manager):
        """save_storage_state and load_storage_state work together."""
        session = session_manager.create("storage-save-test", url="https://example.com")

        storage_state = {
            "cookies": [{"name": "session", "value": "abc"}],
            "origins": [{"origin": "https://example.com", "localStorage": []}]
        }

        # Save storage state
        path = session_manager.save_storage_state("storage-save-test", storage_state)

        assert path.exists()

        # Load storage state
        loaded = session_manager.load_storage_state("storage-save-test")

        assert loaded is not None
        assert loaded["cookies"][0]["name"] == "session"

    def test_session_export_to_agentbrowser(self, session_manager, tmp_path):
        """export_to_agentbrowser creates correct format."""
        from session.manager import SessionState

        session = SessionState(
            session_id="export-test",
            cookies={"session_id": "abc123", "token": "xyz"},
            local_storage={"https://example.com": {"user": "test"}}
        )
        session_manager.save(session)

        output_path = tmp_path / "export.json"
        result = session_manager.export_to_agentbrowser("export-test", output_path)

        assert result is True
        assert output_path.exists()

        data = json.loads(output_path.read_text())
        assert "cookies" in data
        assert "localStorage" in data
        assert len(data["cookies"]) == 2

    def test_session_import_from_agentbrowser(self, session_manager, tmp_path):
        """import_from_agentbrowser loads agent-browser format."""
        # Create agent-browser format file
        state_data = {
            "cookies": [
                {"name": "imported_cookie", "value": "imported_value", "domain": "example.com"}
            ],
            "localStorage": {
                "https://example.com": {"imported_key": "imported_val"}
            }
        }
        state_path = tmp_path / "import.json"
        state_path.write_text(json.dumps(state_data))

        # Import
        session = session_manager.import_from_agentbrowser("import-test", state_path)

        assert session is not None
        assert session.cookies.get("imported_cookie") == "imported_value"
        assert "https://example.com" in session.local_storage
