"""
CAPTCHA Service for Authentication Security.

Implements ISO 27001 A.9.4.2 (Secure log-on procedures) and
A.9.4.4 (Use of privileged utility programs).

Provides numeric CAPTCHA generation and validation with rate limiting
to prevent automated attacks and brute force attempts.

@module security.captcha
"""

import secrets
import string
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from app.core.logging import get_logger

logger = get_logger(__name__)


class CAPTCHADifficulty(str, Enum):
    """CAPTCHA difficulty levels."""
    EASY = "easy"  # 4 digits
    MEDIUM = "medium"  # 6 digits
    HARD = "hard"  # 8 digits


@dataclass
class CAPTCHAChallenge:
    """CAPTCHA challenge data."""
    challenge_id: str
    challenge_text: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    attempts: int = 0
    max_attempts: int = 3


class CAPTCHAManager:
    """
    CAPTCHA manager for bot prevention and rate limiting.

    Features:
    - Numeric CAPTCHA generation (cryptographically secure)
    - Time-based expiration (5 minutes default)
    - Attempt limiting (3 attempts per challenge)
    - IP-based rate limiting
    - Challenge cleanup (auto-expiry)

    ISO 27001 Controls:
    - A.9.4.2: Enhanced log-on security
    - A.14.2.5: Secure system engineering principles
    - A.12.2.1: Protection from malware (bot prevention)

    Example:
        >>> captcha_mgr = CAPTCHAManager()
        >>> challenge_id, text = captcha_mgr.generate_captcha(
        ...     ip_address="192.168.1.100",
        ...     difficulty=CAPTCHADifficulty.MEDIUM
        ... )
        >>> captcha_mgr.validate_captcha(challenge_id, text, "192.168.1.100")
        True
    """

    def __init__(
        self,
        expiry_minutes: int = 5,
        max_attempts: int = 3,
        rate_limit_per_hour: int = 10,
    ):
        """
        Initialize CAPTCHA manager.

        Args:
            expiry_minutes: CAPTCHA expiration time in minutes
            max_attempts: Maximum validation attempts per challenge
            rate_limit_per_hour: Maximum CAPTCHAs generated per IP per hour
        """
        self.expiry_minutes = expiry_minutes
        self.max_attempts = max_attempts
        self.rate_limit_per_hour = rate_limit_per_hour

        # In-memory storage (replace with Redis in production)
        self._challenges: Dict[str, CAPTCHAChallenge] = {}
        self._ip_rate_limit: Dict[str, list[datetime]] = {}

        logger.info(
            "CAPTCHAManager initialized",
            extra={
                "expiry_minutes": expiry_minutes,
                "max_attempts": max_attempts,
                "rate_limit_per_hour": rate_limit_per_hour,
            }
        )

    def generate_captcha(
        self,
        ip_address: Optional[str] = None,
        difficulty: CAPTCHADifficulty = CAPTCHADifficulty.MEDIUM
    ) -> Tuple[str, str]:
        """
        Generate a new numeric CAPTCHA challenge.

        Args:
            ip_address: Client IP address (for rate limiting)
            difficulty: CAPTCHA difficulty level

        Returns:
            Tuple of (challenge_id, challenge_text_display)

        Raises:
            Exception: If rate limit exceeded

        Example:
            >>> mgr = CAPTCHAManager()
            >>> cid, text = mgr.generate_captcha("192.168.1.1", CAPTCHADifficulty.EASY)
            >>> len(text)
            4

        ISO 27001: A.9.4.2 (CAPTCHA generation for secure authentication)
        """
        # Check IP rate limit
        if ip_address:
            if not self._check_rate_limit(ip_address):
                logger.warning(
                    "CAPTCHA rate limit exceeded",
                    extra={"ip_address": ip_address}
                )
                raise Exception(
                    f"Rate limit exceeded. Maximum {self.rate_limit_per_hour} CAPTCHAs per hour."
                )

        # Clean up expired challenges
        self._cleanup_expired_challenges()

        # Determine CAPTCHA length based on difficulty
        length_map = {
            CAPTCHADifficulty.EASY: 4,
            CAPTCHADifficulty.MEDIUM: 6,
            CAPTCHADifficulty.HARD: 8,
        }
        length = length_map[difficulty]

        # Generate cryptographically secure random digits
        challenge_text = ''.join(
            secrets.choice(string.digits) for _ in range(length)
        )

        # Generate unique challenge ID
        challenge_id = self._generate_challenge_id()

        # Create challenge
        now = datetime.utcnow()
        challenge = CAPTCHAChallenge(
            challenge_id=challenge_id,
            challenge_text=challenge_text,
            created_at=now,
            expires_at=now + timedelta(minutes=self.expiry_minutes),
            ip_address=ip_address,
            attempts=0,
            max_attempts=self.max_attempts,
        )

        # Store challenge
        self._challenges[challenge_id] = challenge

        # Update IP rate limit
        if ip_address:
            if ip_address not in self._ip_rate_limit:
                self._ip_rate_limit[ip_address] = []
            self._ip_rate_limit[ip_address].append(now)

        logger.info(
            "CAPTCHA generated",
            extra={
                "challenge_id": challenge_id,
                "difficulty": difficulty.value,
                "length": length,
                "ip_address": ip_address,
                "expires_at": challenge.expires_at.isoformat(),
            }
        )

        # Return formatted display text (e.g., "1234" -> "1 2 3 4")
        display_text = ' '.join(challenge_text)

        return challenge_id, display_text

    def validate_captcha(
        self,
        challenge_id: str,
        user_input: str,
        ip_address: Optional[str] = None
    ) -> bool:
        """
        Validate CAPTCHA response.

        Args:
            challenge_id: CAPTCHA challenge identifier
            user_input: User's input (digits only, spaces ignored)
            ip_address: Client IP address (for logging)

        Returns:
            True if validation successful, False otherwise

        Example:
            >>> mgr = CAPTCHAManager()
            >>> cid, _ = mgr.generate_captcha()
            >>> # Get challenge text from internal storage for testing
            >>> challenge_text = mgr._challenges[cid].challenge_text
            >>> mgr.validate_captcha(cid, challenge_text)
            True

        ISO 27001: A.9.4.2 (CAPTCHA validation)
        """
        # Clean whitespace and non-digits
        user_input_clean = ''.join(c for c in user_input if c.isdigit())

        # Get challenge
        challenge = self._challenges.get(challenge_id)

        if not challenge:
            logger.warning(
                "CAPTCHA validation failed: challenge not found",
                extra={"challenge_id": challenge_id, "ip_address": ip_address}
            )
            return False

        # Check expiration
        if datetime.utcnow() > challenge.expires_at:
            logger.warning(
                "CAPTCHA validation failed: expired",
                extra={
                    "challenge_id": challenge_id,
                    "expired_at": challenge.expires_at.isoformat(),
                    "ip_address": ip_address,
                }
            )
            # Remove expired challenge
            del self._challenges[challenge_id]
            return False

        # Increment attempts
        challenge.attempts += 1

        # Check max attempts
        if challenge.attempts > challenge.max_attempts:
            logger.warning(
                "CAPTCHA validation failed: max attempts exceeded",
                extra={
                    "challenge_id": challenge_id,
                    "attempts": challenge.attempts,
                    "max_attempts": challenge.max_attempts,
                    "ip_address": ip_address,
                }
            )
            # Remove challenge after max attempts
            del self._challenges[challenge_id]
            return False

        # Validate answer (timing-attack resistant comparison)
        is_valid = secrets.compare_digest(
            user_input_clean,
            challenge.challenge_text
        )

        if is_valid:
            logger.info(
                "CAPTCHA validation successful",
                extra={
                    "challenge_id": challenge_id,
                    "attempts": challenge.attempts,
                    "ip_address": ip_address,
                }
            )
            # Remove challenge after successful validation
            del self._challenges[challenge_id]
            return True
        else:
            logger.warning(
                "CAPTCHA validation failed: incorrect answer",
                extra={
                    "challenge_id": challenge_id,
                    "attempts": challenge.attempts,
                    "remaining_attempts": challenge.max_attempts - challenge.attempts,
                    "ip_address": ip_address,
                }
            )
            return False

    def _check_rate_limit(self, ip_address: str) -> bool:
        """
        Check if IP has exceeded rate limit.

        Args:
            ip_address: IP address to check

        Returns:
            True if within limit, False if exceeded
        """
        if ip_address not in self._ip_rate_limit:
            return True

        # Clean old attempts (older than 1 hour)
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        self._ip_rate_limit[ip_address] = [
            ts for ts in self._ip_rate_limit[ip_address]
            if ts > one_hour_ago
        ]

        # Check count
        count = len(self._ip_rate_limit[ip_address])
        return count < self.rate_limit_per_hour

    def _cleanup_expired_challenges(self) -> None:
        """Remove expired challenges from storage."""
        now = datetime.utcnow()
        expired = [
            cid for cid, challenge in self._challenges.items()
            if now > challenge.expires_at
        ]

        for cid in expired:
            del self._challenges[cid]

        if expired:
            logger.debug(
                "Cleaned up expired CAPTCHAs",
                extra={"count": len(expired)}
            )

    def _generate_challenge_id(self) -> str:
        """Generate unique challenge ID."""
        return secrets.token_urlsafe(32)

    def get_challenge_info(self, challenge_id: str) -> Optional[Dict]:
        """
        Get challenge information (for debugging/monitoring).

        Args:
            challenge_id: Challenge identifier

        Returns:
            Challenge info dict or None if not found
        """
        challenge = self._challenges.get(challenge_id)
        if not challenge:
            return None

        return {
            "challenge_id": challenge.challenge_id,
            "created_at": challenge.created_at.isoformat(),
            "expires_at": challenge.expires_at.isoformat(),
            "attempts": challenge.attempts,
            "max_attempts": challenge.max_attempts,
            "remaining_attempts": challenge.max_attempts - challenge.attempts,
            "is_expired": datetime.utcnow() > challenge.expires_at,
        }

    def revoke_challenge(self, challenge_id: str) -> bool:
        """
        Manually revoke/invalidate a challenge.

        Args:
            challenge_id: Challenge identifier

        Returns:
            True if revoked, False if not found
        """
        if challenge_id in self._challenges:
            del self._challenges[challenge_id]
            logger.info(
                "CAPTCHA challenge revoked",
                extra={"challenge_id": challenge_id}
            )
            return True
        return False

    def get_active_challenges_count(self) -> int:
        """Get count of active (non-expired) challenges."""
        self._cleanup_expired_challenges()
        return len(self._challenges)

    def get_ip_captcha_count(self, ip_address: str) -> int:
        """Get count of CAPTCHAs generated by IP in last hour."""
        if ip_address not in self._ip_rate_limit:
            return 0

        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        recent = [
            ts for ts in self._ip_rate_limit[ip_address]
            if ts > one_hour_ago
        ]
        return len(recent)


# Singleton instance
_captcha_manager: Optional[CAPTCHAManager] = None


def get_captcha_manager() -> CAPTCHAManager:
    """
    Get singleton CAPTCHAManager instance.

    Returns:
        CAPTCHAManager instance
    """
    global _captcha_manager

    if _captcha_manager is None:
        _captcha_manager = CAPTCHAManager(
            expiry_minutes=5,
            max_attempts=3,
            rate_limit_per_hour=10,
        )

    return _captcha_manager
