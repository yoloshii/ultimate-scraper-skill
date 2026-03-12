"""Fingerprint persistence package for consistent browser identity per domain."""

from .manager import FingerprintProfile, FingerprintManager

__all__ = ["FingerprintProfile", "FingerprintManager"]
