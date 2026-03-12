"""Tier implementations for multi-level scraping."""

# Note: Imports are done directly in modules to avoid circular imports
# when running as a script. Use:
#   from tiers.tier0_static import Tier0Static
#   etc.

__all__ = [
    "BaseTier",
    "Tier0Static",
    "Tier1HTTP",
    "Tier2Scrapling",
    "Tier3Camoufox",
    "Tier4AI",
]
