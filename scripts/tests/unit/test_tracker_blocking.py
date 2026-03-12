"""Unit tests for tracker blocking patterns."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from detection import TRACKER_PATTERNS


class TestTrackerPatterns:
    """Tests for consolidated TRACKER_PATTERNS."""

    def test_patterns_not_empty(self):
        """Tracker patterns list is populated."""
        assert len(TRACKER_PATTERNS) > 0

    def test_patterns_are_strings(self):
        """All patterns are strings."""
        for p in TRACKER_PATTERNS:
            assert isinstance(p, str), f"Pattern is not string: {p}"

    def test_google_analytics_blocked(self):
        """Google Analytics patterns are included."""
        ga_patterns = [p for p in TRACKER_PATTERNS if "analytics" in p.lower() or "google-analytics" in p.lower()]
        assert len(ga_patterns) > 0

    def test_facebook_pixel_blocked(self):
        """Facebook Connect patterns are included."""
        fb_patterns = [p for p in TRACKER_PATTERNS if "facebook" in p.lower()]
        assert len(fb_patterns) > 0

    def test_fingerprint_scripts_blocked(self):
        """Fingerprinting script patterns are included."""
        fp_patterns = [p for p in TRACKER_PATTERNS if "fingerprint" in p.lower()]
        assert len(fp_patterns) > 0

    def test_no_duplicates(self):
        """No duplicate patterns."""
        assert len(TRACKER_PATTERNS) == len(set(TRACKER_PATTERNS))

    def test_patterns_are_glob_format(self):
        """Patterns use glob wildcard format (** prefix)."""
        glob_patterns = [p for p in TRACKER_PATTERNS if "**" in p]
        assert len(glob_patterns) > 0
