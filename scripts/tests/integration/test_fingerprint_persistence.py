"""Integration tests for fingerprint persistence."""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.integration
class TestFingerprintPersistence:
    """Integration tests for fingerprint database operations."""

    def test_fingerprint_create_and_retrieve(self, fingerprint_manager):
        """Create fingerprint, retrieve same one for same domain."""
        # Create fingerprint
        fp1 = fingerprint_manager.get_or_create("example.com", "us")

        # Retrieve should return same fingerprint
        fp2 = fingerprint_manager.get_for_domain("example.com")

        assert fp2 is not None
        assert fp1.fingerprint_id == fp2.fingerprint_id
        assert fp1.browser == fp2.browser
        assert fp1.user_agent == fp2.user_agent

    def test_fingerprint_different_domains_different_fp(self, fingerprint_manager):
        """Different domains get different fingerprints."""
        fp1 = fingerprint_manager.get_or_create("site1.com", "us")
        fp2 = fingerprint_manager.get_or_create("site2.com", "us")

        assert fp1.fingerprint_id != fp2.fingerprint_id
        assert fp1.domain == "site1.com"
        assert fp2.domain == "site2.com"

    def test_fingerprint_rotation_after_blocks(self, fingerprint_manager):
        """Fingerprint rotates after hitting block threshold."""
        # Create fingerprint with many blocks
        fp = fingerprint_manager.get_or_create("blocked-site.com", "us")
        original_id = fp.fingerprint_id

        # Record many blocks (exceed threshold)
        for _ in range(10):
            fingerprint_manager.record_usage(fp.fingerprint_id, success=False)

        # Next get_or_create should rotate
        fp_new = fingerprint_manager.get_or_create("blocked-site.com", "us")

        assert fp_new.fingerprint_id != original_id

    def test_fingerprint_rotation_after_age(self, fingerprint_manager):
        """Fingerprint rotates after MAX_AGE_DAYS."""
        from fingerprint.manager import FingerprintProfile

        # Create old fingerprint manually
        old_date = (datetime.now() - timedelta(days=35)).isoformat()
        old_fp = FingerprintProfile(
            fingerprint_id="old-fp-12345",
            domain="old-domain.com",
            browser="chrome",
            browser_version="chrome143",
            impersonate="chrome143",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Win32",
            geo="us",
            created_at=old_date,
            last_used_at=old_date,
        )
        fingerprint_manager.save(old_fp)

        # Get should trigger rotation
        new_fp = fingerprint_manager.get_or_create("old-domain.com", "us")

        assert new_fp.fingerprint_id != "old-fp-12345"

    def test_fingerprint_cleanup_old(self, fingerprint_manager):
        """cleanup_old() removes aged fingerprints."""
        from fingerprint.manager import FingerprintProfile

        # Create old fingerprint
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        old_fp = FingerprintProfile(
            fingerprint_id="cleanup-test-fp",
            domain="cleanup.com",
            browser="firefox",
            browser_version="firefox135",
            impersonate="firefox135",
            user_agent="Mozilla/5.0...",
            accept_language="en-US",
            platform="Linux x86_64",
            geo="us",
            created_at=old_date,
            last_used_at=old_date,
        )
        fingerprint_manager.save(old_fp)

        # Cleanup
        deleted = fingerprint_manager.cleanup_old(max_age_days=30)

        assert deleted >= 1

        # Should be gone
        retrieved = fingerprint_manager.get_for_domain("cleanup.com")
        assert retrieved is None

    def test_fingerprint_list_by_domain(self, fingerprint_manager):
        """list_fingerprints(domain) filters correctly."""
        # Create fingerprints for different domains
        fingerprint_manager.get_or_create("filtered1.com", "us")
        fingerprint_manager.get_or_create("filtered2.com", "us")
        fingerprint_manager.get_or_create("filtered1.com", "de")

        # List only for filtered1.com
        fps = fingerprint_manager.list_fingerprints("filtered1.com")

        # Should find at least one (might have rotated)
        assert len(fps) >= 1
        assert all(fp["domain"] == "filtered1.com" for fp in fps)

    def test_fingerprint_save_updates_existing(self, fingerprint_manager):
        """Saving modified fingerprint updates database."""
        from fingerprint.manager import FingerprintProfile

        fp = fingerprint_manager.get_or_create("update-test.com", "us")
        original_use_count = fp.use_count

        # Modify and save
        fp.use_count = 100
        fingerprint_manager.save(fp)

        # Retrieve and verify
        retrieved = fingerprint_manager.get_for_domain("update-test.com")
        assert retrieved.use_count == 100

    def test_fingerprint_multiple_geo(self, fingerprint_manager):
        """Same domain with different geo creates different fingerprints based on browser selection."""
        fp_us = fingerprint_manager.get_or_create("multi-geo.com", "us")

        # The same domain should return the same fingerprint regardless of geo
        # (fingerprint is per-domain, not per-geo)
        fp_de = fingerprint_manager.get_or_create("multi-geo.com", "de")

        # Should return same fingerprint (domain-based)
        assert fp_us.fingerprint_id == fp_de.fingerprint_id

    def test_fingerprint_consistency_across_sessions(self, fingerprint_manager, temp_db, monkeypatch):
        """Fingerprint persists across manager instances."""
        # Create with first manager
        fp1 = fingerprint_manager.get_or_create("persist-test.com", "us")
        fp1_id = fp1.fingerprint_id

        # Create new manager with same DB
        from fingerprint.manager import FingerprintManager
        manager2 = FingerprintManager(db_path=temp_db)

        # Should get same fingerprint
        fp2 = manager2.get_for_domain("persist-test.com")

        assert fp2 is not None
        assert fp2.fingerprint_id == fp1_id
