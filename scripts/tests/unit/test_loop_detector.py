"""Unit tests for ActionLoopDetector and PageFingerprint."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from detection.loop_detector import (
    ActionLoopDetector,
    PageFingerprint,
    compute_action_hash,
)


class TestPageFingerprint:
    """Tests for PageFingerprint."""

    def test_same_url_similarity(self):
        """Same URL gives at least 0.5 similarity."""
        a = PageFingerprint.from_snapshot("https://example.com", {}, 1)
        b = PageFingerprint.from_snapshot("https://example.com", {}, 1)
        assert a.similarity(b) >= 0.5

    def test_different_url_zero_similarity(self):
        """Different URLs give 0.0 similarity."""
        a = PageFingerprint.from_snapshot("https://a.com", {}, 1)
        b = PageFingerprint.from_snapshot("https://b.com", {}, 1)
        assert a.similarity(b) == 0.0

    def test_identical_fingerprints(self):
        """Identical fingerprints give 1.0 similarity."""
        refs = {"@e1": True, "@e2": True}
        a = PageFingerprint.from_snapshot("https://example.com", refs, 1)
        b = PageFingerprint.from_snapshot("https://example.com", refs, 1)
        assert a.similarity(b) == 1.0

    def test_frozen_dataclass(self):
        """PageFingerprint is frozen (immutable)."""
        fp = PageFingerprint.from_snapshot("https://example.com")
        with pytest.raises(AttributeError):
            fp.url_hash = "modified"


class TestComputeActionHash:
    """Tests for compute_action_hash."""

    def test_same_action_same_hash(self):
        """Same action type and data produce same hash."""
        a = compute_action_hash("click", {"selector": "#btn"})
        b = compute_action_hash("click", {"selector": "#btn"})
        assert a == b

    def test_different_action_different_hash(self):
        """Different action types produce different hashes."""
        a = compute_action_hash("click", {"selector": "#btn"})
        b = compute_action_hash("fill", {"selector": "#btn"})
        assert a != b

    def test_strips_unstable_fields(self):
        """session_id and timestamp are stripped from hash."""
        a = compute_action_hash("click", {"selector": "#btn", "session_id": "abc"})
        b = compute_action_hash("click", {"selector": "#btn", "session_id": "xyz"})
        assert a == b

    def test_strips_timestamp(self):
        """timestamp field stripped from hash."""
        a = compute_action_hash("click", {"selector": "#btn", "timestamp": 100})
        b = compute_action_hash("click", {"selector": "#btn", "timestamp": 200})
        assert a == b

    def test_none_data(self):
        """None action data produces valid hash."""
        h = compute_action_hash("click", None)
        assert len(h) == 12


class TestActionLoopDetector:
    """Tests for ActionLoopDetector."""

    @pytest.fixture
    def detector(self):
        return ActionLoopDetector(
            window_size=10,
            warning_threshold=3,
            stuck_threshold=5,
            critical_threshold=7,
        )

    def test_no_warning_initially(self, detector):
        """No warning with few actions."""
        assert detector.record("click", {"selector": "#a"}) is None
        assert detector.record("click", {"selector": "#b"}) is None

    def test_warning_on_repeats(self, detector):
        """WARNING after 3 identical actions."""
        for _ in range(3):
            result = detector.record("click", {"selector": "#btn"})
        assert result is not None
        assert "WARNING" in result

    def test_stuck_on_more_repeats(self, detector):
        """STUCK after 5 identical actions."""
        result = None
        for _ in range(5):
            result = detector.record("click", {"selector": "#btn"})
        assert result is not None
        assert "STUCK" in result

    def test_critical_on_many_repeats(self, detector):
        """CRITICAL after 7 identical actions."""
        result = None
        for _ in range(7):
            result = detector.record("click", {"selector": "#btn"})
        assert result is not None
        assert "CRITICAL" in result

    def test_reset_clears_state(self, detector):
        """reset() clears detection history."""
        for _ in range(3):
            detector.record("click", {"selector": "#btn"})
        detector.reset()
        assert detector.record("click", {"selector": "#btn"}) is None

    def test_varied_actions_no_warning(self, detector):
        """Different actions don't trigger warnings."""
        detector.record("click", {"selector": "#a"})
        detector.record("fill", {"selector": "#b", "text": "hello"})
        detector.record("scroll", {"direction": "down"})
        detector.record("click", {"selector": "#c"})
        result = detector.record("press", {"key": "Enter"})
        assert result is None
