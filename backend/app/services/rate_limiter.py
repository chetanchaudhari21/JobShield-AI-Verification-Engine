"""Abuse Prevention, Rate Limiting, and Privacy Hashing for Community Feedback (F8 & F9).

Provides:
- In-memory sliding-window rate limiter with burst protection.
- Privacy-preserving submitter hashing (never store raw client IPs).
- Cryptographic content hashing for duplicate submission detection.
"""

from collections import deque
from datetime import datetime, timezone
import hashlib
import threading
import time
from typing import Dict, Optional, Tuple

from app.core.config import settings


class SlidingWindowRateLimiter:
    """Thread-safe sliding-window rate limiter with burst throttling."""

    def __init__(
        self,
        max_requests: int = 5,
        window_seconds: int = 60,
        burst_limit: int = 3,
        burst_seconds: int = 10,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.burst_limit = burst_limit
        self.burst_seconds = burst_seconds
        self._history: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def check_and_record(self, key: str) -> Tuple[bool, Optional[str]]:
        """Checks if a request is allowed under rate and burst limits.

        If allowed, records the request timestamp.
        Returns (is_allowed, error_message).
        """
        now = time.time()

        with self._lock:
            if key not in self._history:
                self._history[key] = deque()

            q = self._history[key]

            # Evict timestamps older than window_seconds
            while q and (now - q[0]) > self.window_seconds:
                q.popleft()

            # Burst check (requests within burst_seconds)
            burst_count = sum(1 for ts in q if (now - ts) <= self.burst_seconds)
            if burst_count >= self.burst_limit:
                retry_after = int(self.burst_seconds - (now - q[-self.burst_limit])) + 1
                return False, f"Burst rate limit exceeded. Please wait {max(1, retry_after)} seconds before trying again."

            # Window check (requests within window_seconds)
            if len(q) >= self.max_requests:
                retry_after = int(self.window_seconds - (now - q[0])) + 1
                return False, f"Submission rate limit exceeded (maximum {self.max_requests} per minute). Please try again in {max(1, retry_after)} seconds."

            # Allowed - record timestamp
            q.append(now)
            return True, None

    def reset_for_test(self, key: Optional[str] = None) -> None:
        """Helper for test suites to reset rate limit state."""
        with self._lock:
            if key:
                self._history.pop(key, None)
            else:
                self._history.clear()


# Global rate limiter instance configured from settings
community_rate_limiter = SlidingWindowRateLimiter(
    max_requests=settings.COMMUNITY_RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
    burst_limit=3,
    burst_seconds=10,
)


def hash_submitter(ip: str, salt: Optional[str] = None) -> str:
    """Computes a salted cryptographic SHA-256 hash of submitter identifier.

    CRITICAL PRIVACY RULE: Never store raw IP addresses or identifiable tokens.
    """
    clean_ip = (ip or "127.0.0.1").strip()
    active_salt = salt or settings.COMMUNITY_SALT
    salted = f"{active_salt}:{clean_ip}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def compute_review_content_hash(
    target: str,
    rating: int,
    category: str,
    text: Optional[str],
) -> str:
    """Computes SHA-256 hash of normalized review content for duplicate detection."""
    clean_target = (target or "").strip().lower()
    clean_category = (category or "").strip().lower()
    clean_text = (text or "").strip().lower()
    canonical = f"review|{clean_target}|{rating}|{clean_category}|{clean_text}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_report_content_hash(
    target: str,
    report_type: str,
    details: str,
) -> str:
    """Computes SHA-256 hash of normalized fraud report for duplicate detection."""
    clean_target = (target or "").strip().lower()
    clean_type = (report_type or "").strip().lower()
    clean_details = (details or "").strip().lower()
    canonical = f"report|{clean_target}|{clean_type}|{clean_details}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
