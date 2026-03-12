"""Action loop detection for agent tiers.

Detects when browser tiers get stuck repeating the same actions.
Ported from browser-use/scripts/models.py (ActionLoopDetector, PageFingerprint).
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PageFingerprint:
    """Lightweight page identity for loop detection."""

    url_hash: str
    interactive_count: int
    tab_count: int
    top_ref_keys: tuple = ()

    @classmethod
    def from_snapshot(
        cls,
        url: str,
        refs: Optional[dict] = None,
        tab_count: int = 1,
    ) -> PageFingerprint:
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
        ref_keys = tuple(sorted((refs or {}).keys())[:10])
        return cls(
            url_hash=url_hash,
            interactive_count=len(refs) if refs else 0,
            tab_count=tab_count,
            top_ref_keys=ref_keys,
        )

    def similarity(self, other: PageFingerprint) -> float:
        """0.0 (completely different) to 1.0 (identical)."""
        if self.url_hash != other.url_hash:
            return 0.0
        score = 0.5  # Same URL
        if self.interactive_count == other.interactive_count:
            score += 0.2
        if self.tab_count == other.tab_count:
            score += 0.1
        if self.top_ref_keys and other.top_ref_keys:
            overlap = len(set(self.top_ref_keys) & set(other.top_ref_keys))
            max_len = max(len(self.top_ref_keys), len(other.top_ref_keys))
            if max_len > 0:
                score += 0.2 * (overlap / max_len)
        return min(score, 1.0)


# Fields that change across invocations but don't affect action identity
_UNSTABLE_FIELDS = frozenset({"session_id", "timestamp", "request_id", "trace_id", "id"})


def compute_action_hash(action_type: str, action_data: any = None) -> str:
    """Deterministic hash of an action for loop detection.

    Strips unstable fields (session_id, timestamp, etc.) so identical
    logical actions produce the same hash across invocations.
    """
    key = action_type
    if action_data:
        if isinstance(action_data, dict):
            stable = {k: v for k, v in action_data.items() if k not in _UNSTABLE_FIELDS}
            key += json.dumps(stable, sort_keys=True, default=str)
        else:
            key += str(action_data)
    return hashlib.sha256(key.encode()).hexdigest()[:12]


class ActionLoopDetector:
    """Detect stuck agent by tracking repeated action + page state patterns.

    Escalating warnings:
      - WARNING (3 repeats): "Try different approach"
      - STUCK (5 repeats): "Not working — escalate"
      - CRITICAL (7 repeats): "Infinite loop — abort"
    """

    def __init__(
        self,
        window_size: int = 10,
        warning_threshold: int = 3,
        stuck_threshold: int = 5,
        critical_threshold: int = 7,
    ):
        self._history: deque[tuple[str, PageFingerprint]] = deque(maxlen=window_size)
        self._warning_threshold = warning_threshold
        self._stuck_threshold = stuck_threshold
        self._critical_threshold = critical_threshold

    def record(
        self,
        action_type: str,
        action_data: any = None,
        page_fingerprint: Optional[PageFingerprint] = None,
    ) -> Optional[str]:
        """Record an action and return a warning string if loop detected.

        Args:
            action_type: The action name (click, fill, scroll, etc.)
            action_data: Action parameters for hashing
            page_fingerprint: Current page state (optional)

        Returns:
            None if no loop, or warning string at WARNING/STUCK/CRITICAL level.
        """
        action_hash = compute_action_hash(action_type, action_data)
        fp = page_fingerprint or PageFingerprint(url_hash="", interactive_count=0, tab_count=1)

        self._history.append((action_hash, fp))

        if len(self._history) < self._warning_threshold:
            return None

        # Count repetitions of the current action+state pattern
        current_hash = action_hash
        repeat_count = 0
        for past_hash, past_fp in self._history:
            if past_hash == current_hash and fp.similarity(past_fp) >= 0.79:
                repeat_count += 1

        if repeat_count >= self._critical_threshold:
            return (
                f"[CRITICAL] Infinite loop detected: action repeated {repeat_count} times "
                f"with same page state. Abort immediately."
            )
        if repeat_count >= self._stuck_threshold:
            return (
                f"[STUCK] Action repeated {repeat_count} times with same page state. "
                f"Not working — escalate to next tier."
            )
        if repeat_count >= self._warning_threshold:
            return (
                f"[WARNING] Action repeated {repeat_count} times. "
                f"Try a different approach."
            )

        return None

    def reset(self) -> None:
        """Reset detection state (e.g., after cross-domain navigation)."""
        self._history.clear()
