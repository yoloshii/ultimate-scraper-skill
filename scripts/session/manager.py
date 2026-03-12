"""Session persistence for cross-request state management."""

import sqlite3
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional
from core.config import get_config


@dataclass
class SessionState:
    """Complete session state for persistence."""

    session_id: str
    url: str = ""
    tier_used: int = -1

    # Browser state
    cookies: dict = field(default_factory=dict)
    local_storage: dict = field(default_factory=dict)  # origin -> {key: value}
    storage_state_path: str = ""  # For Playwright/Camoufox

    # Proxy state
    proxy_session_id: str = ""
    proxy_geo: str = ""

    # Fingerprint persistence
    fingerprint_id: str = ""  # Links to FingerprintProfile for consistent identity

    # Element refs (for action sequences)
    ref_map: dict = field(default_factory=dict)

    # Debug info
    console_messages: list = field(default_factory=list)
    page_errors: list = field(default_factory=list)
    tracked_requests: list = field(default_factory=list)

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Create from dictionary."""
        return cls(**data)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now().isoformat()


class SessionManager:
    """Manage persistent sessions across scraping requests."""

    def __init__(self, db_path: Optional[Path] = None, max_age_hours: int = 24):
        config = get_config()
        self.session_dir = config.session_dir
        self.db_path = db_path or config.cache_dir / "sessions.db"
        self.max_age_hours = max_age_hours
        self._init_db()

    def _init_db(self) -> None:
        """Initialize session database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                url TEXT,
                tier_used INTEGER,
                cookies TEXT,
                local_storage TEXT,
                storage_state_path TEXT,
                proxy_session_id TEXT,
                proxy_geo TEXT,
                fingerprint_id TEXT,
                ref_map TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_expires ON sessions(expires_at)
        """)
        conn.commit()
        conn.close()

    def get(self, session_id: str) -> Optional[SessionState]:
        """Load session state by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT session_id, url, tier_used, cookies, local_storage,
                   storage_state_path, proxy_session_id, proxy_geo, fingerprint_id,
                   ref_map, created_at, updated_at
            FROM sessions
            WHERE session_id = ? AND expires_at > ?
            """,
            (session_id, datetime.now().isoformat())
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            return SessionState(
                session_id=row[0],
                url=row[1] or "",
                tier_used=row[2] or -1,
                cookies=json.loads(row[3]) if row[3] else {},
                local_storage=json.loads(row[4]) if row[4] else {},
                storage_state_path=row[5] or "",
                proxy_session_id=row[6] or "",
                proxy_geo=row[7] or "",
                fingerprint_id=row[8] or "",
                ref_map=json.loads(row[9]) if row[9] else {},
                created_at=row[10],
                updated_at=row[11],
            )
        return None

    def save(self, state: SessionState) -> None:
        """Save session state."""
        state.touch()
        expires = datetime.now() + timedelta(hours=self.max_age_hours)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO sessions
            (session_id, url, tier_used, cookies, local_storage, storage_state_path,
             proxy_session_id, proxy_geo, fingerprint_id, ref_map, created_at, updated_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                state.session_id,
                state.url,
                state.tier_used,
                json.dumps(state.cookies),
                json.dumps(state.local_storage),
                state.storage_state_path,
                state.proxy_session_id,
                state.proxy_geo,
                state.fingerprint_id,
                json.dumps(state.ref_map),
                state.created_at,
                state.updated_at,
                expires.isoformat(),
            )
        )
        conn.commit()
        conn.close()

    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        # Delete storage state file if exists
        session = self.get(session_id)
        if session and session.storage_state_path:
            storage_path = Path(session.storage_state_path)
            if storage_path.exists():
                storage_path.unlink()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM sessions WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()
        deleted = cursor.rowcount > 0
        conn.close()
        return deleted

    def create(self, session_id: str, url: str = "", proxy_geo: str = "") -> SessionState:
        """Create a new session."""
        state = SessionState(
            session_id=session_id,
            url=url,
            proxy_geo=proxy_geo,
        )
        self.save(state)
        return state

    def get_or_create(self, session_id: str, url: str = "", proxy_geo: str = "") -> SessionState:
        """Get existing session or create new one."""
        existing = self.get(session_id)
        if existing:
            return existing
        return self.create(session_id, url, proxy_geo)

    def update_cookies(self, session_id: str, cookies: dict) -> bool:
        """Update session cookies."""
        session = self.get(session_id)
        if session:
            session.cookies.update(cookies)
            self.save(session)
            return True
        return False

    def get_storage_state_path(self, session_id: str) -> Path:
        """Get path for Playwright/Camoufox storage state file."""
        return self.session_dir / f"{session_id}_storage.json"

    def save_storage_state(self, session_id: str, storage_state: dict) -> Path:
        """Save Playwright storage state to file."""
        path = self.get_storage_state_path(session_id)
        path.write_text(json.dumps(storage_state, indent=2))

        # Update session record
        session = self.get(session_id)
        if session:
            session.storage_state_path = str(path)
            self.save(session)

        return path

    def load_storage_state(self, session_id: str) -> Optional[dict]:
        """Load Playwright storage state from file."""
        session = self.get(session_id)
        if session and session.storage_state_path:
            path = Path(session.storage_state_path)
            if path.exists():
                return json.loads(path.read_text())
        return None

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns count of deleted sessions."""
        # Get expired sessions with storage state files
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT session_id, storage_state_path FROM sessions WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        expired = cursor.fetchall()

        # Delete storage state files
        for session_id, storage_path in expired:
            if storage_path:
                path = Path(storage_path)
                if path.exists():
                    path.unlink()

        # Delete from database
        cursor = conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        conn.commit()
        deleted = cursor.rowcount
        conn.close()
        return deleted

    def list_sessions(self) -> list[dict]:
        """List all active sessions."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            """
            SELECT session_id, url, tier_used, proxy_geo, created_at, updated_at
            FROM sessions
            WHERE expires_at > ?
            ORDER BY updated_at DESC
            """,
            (datetime.now().isoformat(),)
        )
        sessions = []
        for row in cursor.fetchall():
            sessions.append({
                "session_id": row[0],
                "url": row[1],
                "tier_used": row[2],
                "proxy_geo": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            })
        conn.close()
        return sessions

    # =========================================================================
    # Agent-browser state compatibility
    # =========================================================================

    def export_to_agentbrowser(self, session_id: str, output_path: Path) -> bool:
        """
        Export session state to agent-browser compatible JSON format.

        Format:
        {
            "cookies": [...],
            "localStorage": {...},
            "sessionStorage": {...},
            "origins": [...]
        }
        """
        session = self.get(session_id)
        if not session:
            return False

        # Build agent-browser state format
        state = {
            "cookies": [],
            "localStorage": {},
            "sessionStorage": {},
            "origins": [],
        }

        # Convert cookies dict to list format
        for name, value in session.cookies.items():
            state["cookies"].append({
                "name": name,
                "value": value,
                "domain": "",  # Would need URL parsing for proper domain
                "path": "/",
                "expires": -1,
                "httpOnly": False,
                "secure": False,
                "sameSite": "Lax",
            })

        # Add localStorage by origin
        for origin, storage in session.local_storage.items():
            state["localStorage"][origin] = storage
            if origin not in state["origins"]:
                state["origins"].append(origin)

        output_path.write_text(json.dumps(state, indent=2))
        return True

    def import_from_agentbrowser(self, session_id: str, state_path: Path) -> Optional[SessionState]:
        """
        Import session state from agent-browser JSON format.

        Reads the format saved by `agent-browser state save`.
        """
        if not state_path.exists():
            return None

        try:
            data = json.loads(state_path.read_text())
        except json.JSONDecodeError:
            return None

        # Create or get session
        session = self.get_or_create(session_id)

        # Import cookies (list to dict)
        if "cookies" in data:
            for cookie in data["cookies"]:
                if "name" in cookie and "value" in cookie:
                    session.cookies[cookie["name"]] = cookie["value"]

        # Import localStorage
        if "localStorage" in data:
            session.local_storage.update(data["localStorage"])

        # Store reference to original state file
        session.storage_state_path = str(state_path)

        self.save(session)
        return session

    def sync_with_agentbrowser(self, session_id: str) -> bool:
        """
        Sync session state with agent-browser CLI.

        Saves current session to agent-browser format and loads it.
        """
        import subprocess

        session = self.get(session_id)
        if not session:
            return False

        # Export to temp file
        state_path = self.get_storage_state_path(session_id)
        if not self.export_to_agentbrowser(session_id, state_path):
            return False

        # Load into agent-browser
        try:
            result = subprocess.run(
                ["agent-browser", "--session", session_id, "state", "load", str(state_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def capture_from_agentbrowser(self, session_id: str) -> Optional[SessionState]:
        """
        Capture current agent-browser session state into our session manager.
        """
        import subprocess

        state_path = self.get_storage_state_path(session_id)

        try:
            # Save state from agent-browser
            result = subprocess.run(
                ["agent-browser", "--session", session_id, "state", "save", str(state_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                return None

            # Import into our session
            return self.import_from_agentbrowser(session_id, state_path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return None
