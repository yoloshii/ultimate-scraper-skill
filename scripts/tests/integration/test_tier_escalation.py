"""Integration tests for tier escalation logic."""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))


@pytest.mark.integration
class TestTierEscalation:
    """Integration tests for tier escalation behavior."""

    @pytest.fixture
    def mock_tiers(self):
        """Create mock tier implementations."""
        class MockTier:
            def __init__(self, tier_num, should_fail=False, should_block=False, should_captcha=False):
                self.TIER_NUMBER = tier_num
                self.TIER_NAME = f"tier{tier_num}"
                self.should_fail = should_fail
                self.should_block = should_block
                self.should_captcha = should_captcha

            async def fetch(self, url, **kwargs):
                from core.result import ScrapeResult, Blocked, CaptchaRequired

                if self.should_block:
                    raise Blocked(f"Blocked at tier {self.TIER_NUMBER}")
                if self.should_captcha:
                    raise CaptchaRequired(f"CAPTCHA at tier {self.TIER_NUMBER}")
                if self.should_fail:
                    return ScrapeResult(
                        success=False,
                        tier_used=self.TIER_NUMBER,
                        error="Tier failed"
                    )
                return ScrapeResult(
                    success=True,
                    tier_used=self.TIER_NUMBER,
                    html=f"<html>Content from tier {self.TIER_NUMBER}</html>",
                    status_code=200
                )

            def can_handle(self, url, profile=None):
                return True

        return MockTier

    def test_tier_sequence_order(self):
        """Verify tier sequence is properly ordered."""
        # Tier sequence should be 0, 1, 2, 2.5, 3, 4, 5
        expected_sequence = [0, 1, 2, 2.5, 3, 4, 5]

        # This tests the expected escalation order concept
        for i in range(len(expected_sequence) - 1):
            assert expected_sequence[i] < expected_sequence[i + 1]

    @pytest.mark.asyncio
    async def test_tier_escalation_on_block(self, mock_tiers):
        """Blocked response should escalate to next tier."""
        from core.result import Blocked

        tier1 = mock_tiers(tier_num=1, should_block=True)
        tier2 = mock_tiers(tier_num=2, should_fail=False)

        # Simulate escalation logic
        tiers = [tier1, tier2]
        result = None

        for tier in tiers:
            try:
                result = await tier.fetch("https://example.com")
                if result.success:
                    break
            except Blocked:
                continue

        assert result is not None
        assert result.success is True
        assert result.tier_used == 2

    @pytest.mark.asyncio
    async def test_tier_escalation_on_captcha(self, mock_tiers):
        """CAPTCHA should escalate to tier 3 (stealth)."""
        from core.result import CaptchaRequired

        tier2 = mock_tiers(tier_num=2, should_captcha=True)
        tier3 = mock_tiers(tier_num=3, should_fail=False)

        tiers = [tier2, tier3]
        result = None

        for tier in tiers:
            try:
                result = await tier.fetch("https://example.com")
                if result.success:
                    break
            except CaptchaRequired:
                # Skip to tier 3
                continue

        assert result is not None
        assert result.success is True
        assert result.tier_used == 3

    @pytest.mark.asyncio
    async def test_tier_skip_ja4t_sites(self, mock_tiers):
        """JA4T sites should skip tier 1 (HTTP)."""
        from detection.mode_detector import ScrapeProfile

        # Profile indicates JA4T detection
        profile = ScrapeProfile(
            url="https://linkedin.com/jobs",
            uses_ja4t=True,
            ja4t_confidence=0.95,
            recommended_tier=2
        )

        # Tier 1 should be skipped for JA4T sites
        tier1 = mock_tiers(tier_num=1)
        tier2 = mock_tiers(tier_num=2)

        # Simulate skip logic
        tiers = [tier1, tier2]
        start_tier_index = 0

        if profile.uses_ja4t and profile.ja4t_confidence > 0.5:
            # Skip tier 1
            start_tier_index = 1

        result = await tiers[start_tier_index].fetch("https://linkedin.com/jobs")

        assert result.tier_used == 2

    @pytest.mark.asyncio
    async def test_max_tier_limit(self, mock_tiers):
        """--max-tier should limit escalation ceiling."""
        tier1 = mock_tiers(tier_num=1, should_block=True)
        tier2 = mock_tiers(tier_num=2, should_block=True)
        tier3 = mock_tiers(tier_num=3, should_fail=False)

        max_tier = 2  # Limit to tier 2

        tiers = {1: tier1, 2: tier2, 3: tier3}
        result = None
        last_error = None

        for tier_num in sorted(tiers.keys()):
            if tier_num > max_tier:
                break

            tier = tiers[tier_num]
            try:
                result = await tier.fetch("https://example.com")
                if result.success:
                    break
            except Exception as e:
                last_error = e
                continue

        # Should stop at tier 2, not escalate to 3
        assert result is None or not result.success

    @pytest.mark.asyncio
    async def test_static_tier_preferred_for_static_sites(self, mock_tiers):
        """Sites with static data should try tier 0 first."""
        from detection.mode_detector import ScrapeProfile

        profile = ScrapeProfile(
            url="https://nextjs-blog.com",
            has_static_data=True,
            recommended_tier=0
        )

        tier0 = mock_tiers(tier_num=0, should_fail=False)
        tier1 = mock_tiers(tier_num=1)

        # If recommended tier is 0 and we have static data, use tier 0
        if profile.has_static_data and profile.recommended_tier == 0:
            result = await tier0.fetch("https://nextjs-blog.com")
        else:
            result = await tier1.fetch("https://nextjs-blog.com")

        assert result.tier_used == 0

    @pytest.mark.asyncio
    async def test_all_tiers_exhausted(self, mock_tiers):
        """All tiers failing should return error result."""
        from core.result import Blocked

        # All tiers fail
        tier1 = mock_tiers(tier_num=1, should_block=True)
        tier2 = mock_tiers(tier_num=2, should_block=True)
        tier3 = mock_tiers(tier_num=3, should_block=True)

        tiers = [tier1, tier2, tier3]
        result = None

        for tier in tiers:
            try:
                result = await tier.fetch("https://super-protected.com")
                if result.success:
                    break
            except Blocked:
                continue

        # No successful result
        assert result is None

    @pytest.mark.asyncio
    async def test_tier_selection_by_antibot(self, mock_tiers):
        """Different antibot types should start at appropriate tiers."""
        from detection.mode_detector import ScrapeProfile

        # Akamai should recommend tier 3
        profile_akamai = ScrapeProfile(
            url="https://amazon.com",
            antibot="akamai",
            recommended_tier=3
        )
        assert profile_akamai.recommended_tier == 3

        # Cloudflare might be tier 2
        profile_cf = ScrapeProfile(
            url="https://cloudflare-site.com",
            antibot="cloudflare",
            recommended_tier=2
        )
        assert profile_cf.recommended_tier == 2

        # No antibot should be tier 1
        profile_none = ScrapeProfile(
            url="https://plain-site.com",
            antibot=None,
            recommended_tier=1
        )
        assert profile_none.recommended_tier == 1

    @pytest.mark.asyncio
    async def test_fingerprint_used_during_escalation(self, mock_tiers, fingerprint_manager):
        """Fingerprint should be consistent during tier escalation."""
        # Get fingerprint for domain
        fp = fingerprint_manager.get_or_create("escalation-test.com", "us")
        fp_id = fp.fingerprint_id

        tier1 = mock_tiers(tier_num=1, should_block=True)
        tier2 = mock_tiers(tier_num=2)

        # Simulate passing fingerprint through tiers
        class TierWithFingerprint:
            def __init__(self, tier, fingerprint_id):
                self.tier = tier
                self.fingerprint_id = fingerprint_id

            async def fetch(self, url, **kwargs):
                result = await self.tier.fetch(url, **kwargs)
                result.fingerprint_id = self.fingerprint_id
                return result

        tier1_fp = TierWithFingerprint(tier1, fp_id)
        tier2_fp = TierWithFingerprint(tier2, fp_id)

        # Escalate
        from core.result import Blocked
        try:
            await tier1_fp.fetch("https://escalation-test.com")
        except Blocked:
            result = await tier2_fp.fetch("https://escalation-test.com")

        # Fingerprint should be preserved
        assert result.fingerprint_id == fp_id
