"""
Password management service.

Implements ISO 27001 A.9.4.3 (Password management system) and
A.9.2.4 (Management of secret authentication information).

Uses Argon2id for password hashing (OWASP recommendation).

@module security.password
"""

import secrets
import string
from typing import Optional, List
from datetime import datetime, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash

from app.core.logging import get_logger
from .models import PasswordPolicy

logger = get_logger(__name__)


class PasswordManager:
    """
    Secure password management with hashing and policy enforcement.

    Uses Argon2id algorithm (winner of Password Hashing Competition 2015):
    - Time cost: 2 iterations
    - Memory cost: 65536 KB (64 MB)
    - Parallelism: 4 threads
    - Salt: 16 bytes (cryptographically random)
    - Output: 32 bytes

    ISO 27001 Controls:
    - A.9.4.3: Password management system
    - A.9.2.4: Management of secret authentication information
    """

    def __init__(self, policy: Optional[PasswordPolicy] = None):
        """
        Initialize password manager.

        Args:
            policy: Password policy configuration
        """
        self.policy = policy or PasswordPolicy()

        # Initialize Argon2id hasher
        # Parameters follow OWASP recommendations (2025)
        self.hasher = PasswordHasher(
            time_cost=2,  # Number of iterations
            memory_cost=65536,  # 64 MB memory usage
            parallelism=4,  # Number of parallel threads
            hash_len=32,  # Output hash length in bytes
            salt_len=16,  # Salt length in bytes
            encoding='utf-8',
        )

        logger.info(
            "PasswordManager initialized",
            extra={
                "algorithm": "argon2id",
                "policy": self.policy.model_dump(),
            }
        )

    def hash_password(self, password: str) -> str:
        """
        Hash a password using Argon2id.

        Args:
            password: Plain text password

        Returns:
            Hashed password (Argon2id format)

        Raises:
            ValueError: If password is empty or None

        Example:
            >>> pm = PasswordManager()
            >>> hashed = pm.hash_password("SecureP@ssw0rd2025!")
            >>> hashed.startswith("$argon2id$")
            True

        ISO 27001: A.9.2.4 (Cryptographic hashing for password storage)
        """
        if not password:
            raise ValueError("Password cannot be empty")

        try:
            hashed = self.hasher.hash(password)

            logger.debug(
                "Password hashed successfully",
                extra={
                    "algorithm": "argon2id",
                    "hash_length": len(hashed),
                }
            )

            return hashed

        except Exception as e:
            logger.error(
                "Password hashing failed",
                extra={"error": str(e)},
                exc_info=True
            )
            raise

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """
        Verify a password against its hash.

        Args:
            plain_password: Plain text password
            hashed_password: Hashed password to verify against

        Returns:
            True if password matches, False otherwise

        Example:
            >>> pm = PasswordManager()
            >>> hashed = pm.hash_password("SecureP@ssw0rd2025!")
            >>> pm.verify_password("SecureP@ssw0rd2025!", hashed)
            True
            >>> pm.verify_password("WrongPassword", hashed)
            False

        ISO 27001: A.9.4.2 (Secure authentication)
        """
        if not plain_password or not hashed_password:
            return False

        try:
            # Verify password
            self.hasher.verify(hashed_password, plain_password)

            logger.debug("Password verification successful")

            return True

        except (VerifyMismatchError, VerificationError, InvalidHash):
            logger.debug("Password verification failed")
            return False

        except Exception as e:
            logger.error(
                "Password verification error",
                extra={"error": str(e)},
                exc_info=True
            )
            return False

    def needs_rehash(self, hashed_password: str) -> bool:
        """
        Check if password hash needs to be updated with current parameters.

        This allows for transparent password hash upgrades when parameters change.

        Args:
            hashed_password: Hashed password to check

        Returns:
            True if hash needs update, False otherwise

        Example:
            >>> pm = PasswordManager()
            >>> old_hash = "$argon2id$v=19$m=4096,t=3,p=1$..."  # Old parameters
            >>> pm.needs_rehash(old_hash)
            True

        ISO 27001: A.10.1.2 (Cryptographic key management - key rotation)
        """
        try:
            return self.hasher.check_needs_rehash(hashed_password)
        except Exception:
            # If we can't parse the hash, assume it needs rehashing
            return True

    def validate_password_policy(self, password: str) -> tuple[bool, List[str]]:
        """
        Validate password against policy requirements.

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, list_of_errors)

        Example:
            >>> pm = PasswordManager()
            >>> is_valid, errors = pm.validate_password_policy("weak")
            >>> is_valid
            False
            >>> "Password must be at least" in errors[0]
            True

        ISO 27001: A.9.4.3 (Password management system)
        """
        errors = []

        # Check minimum length
        if len(password) < self.policy.min_length:
            errors.append(
                f"Password must be at least {self.policy.min_length} characters long"
            )

        # Check uppercase requirement
        if self.policy.require_uppercase and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        # Check lowercase requirement
        if self.policy.require_lowercase and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        # Check digit requirement
        if self.policy.require_digit and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")

        # Check special character requirement
        if self.policy.require_special:
            special_chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
            if not any(c in special_chars for c in password):
                errors.append("Password must contain at least one special character")

        # Check for common weak passwords (top 100)
        weak_passwords = [
            "password", "123456", "password123", "admin", "administrator",
            "root", "toor", "pass", "test", "guest", "welcome",
            "Password123!", "Admin123!", "Welcome123!", "Qwerty123!",
            "P@ssw0rd", "P@ssw0rd123", "Password1!", "Admin1!",
        ]
        if password.lower() in [p.lower() for p in weak_passwords]:
            errors.append("Password is too common, please choose a stronger password")

        # Check for sequential characters
        sequences = ["abcd", "1234", "qwer", "asdf", "zxcv"]
        password_lower = password.lower()
        for seq in sequences:
            if seq in password_lower or seq[::-1] in password_lower:
                errors.append("Password contains sequential characters")
                break

        is_valid = len(errors) == 0

        if is_valid:
            logger.debug("Password policy validation passed")
        else:
            logger.debug(
                "Password policy validation failed",
                extra={"errors": errors}
            )

        return is_valid, errors

    def generate_strong_password(self, length: Optional[int] = None) -> str:
        """
        Generate a cryptographically random strong password.

        Args:
            length: Password length (default: policy minimum + 4)

        Returns:
            Strong random password

        Example:
            >>> pm = PasswordManager()
            >>> password = pm.generate_strong_password(16)
            >>> len(password)
            16
            >>> is_valid, _ = pm.validate_password_policy(password)
            >>> is_valid
            True

        ISO 27001: A.9.2.4 (Secure password generation)
        """
        if length is None:
            length = self.policy.min_length + 4

        # Ensure minimum length
        length = max(length, self.policy.min_length)

        # Character sets
        uppercase = string.ascii_uppercase
        lowercase = string.ascii_lowercase
        digits = string.digits
        special = "!@#$%^&*()_+-=[]{}|;:,.<>?"

        # Ensure at least one character from each required set
        password_chars = []

        if self.policy.require_uppercase:
            password_chars.append(secrets.choice(uppercase))

        if self.policy.require_lowercase:
            password_chars.append(secrets.choice(lowercase))

        if self.policy.require_digit:
            password_chars.append(secrets.choice(digits))

        if self.policy.require_special:
            password_chars.append(secrets.choice(special))

        # Fill remaining length with random characters from all sets
        all_chars = ""
        if self.policy.require_uppercase:
            all_chars += uppercase
        if self.policy.require_lowercase:
            all_chars += lowercase
        if self.policy.require_digit:
            all_chars += digits
        if self.policy.require_special:
            all_chars += special

        remaining_length = length - len(password_chars)
        password_chars.extend(
            secrets.choice(all_chars) for _ in range(remaining_length)
        )

        # Shuffle to avoid predictable patterns
        secrets.SystemRandom().shuffle(password_chars)

        password = ''.join(password_chars)

        logger.info(
            "Strong password generated",
            extra={"length": length}
        )

        return password

    def is_password_expired(
        self,
        last_password_change: Optional[datetime]
    ) -> bool:
        """
        Check if password has expired according to policy.

        Args:
            last_password_change: Timestamp of last password change

        Returns:
            True if password is expired, False otherwise

        Example:
            >>> pm = PasswordManager()
            >>> old_date = datetime.now() - timedelta(days=100)
            >>> pm.is_password_expired(old_date)
            True

        ISO 27001: A.9.4.3 (Password expiration policy)
        """
        if last_password_change is None:
            # No record of password change, consider it expired
            return True

        expiration_date = last_password_change + timedelta(
            days=self.policy.max_age_days
        )

        is_expired = datetime.now() >= expiration_date

        if is_expired:
            logger.info(
                "Password expired",
                extra={
                    "last_change": last_password_change.isoformat(),
                    "expiration_date": expiration_date.isoformat(),
                }
            )

        return is_expired

    def is_password_in_history(
        self,
        new_password: str,
        password_history: List[str]
    ) -> bool:
        """
        Check if new password matches any in password history.

        Args:
            new_password: New password to check
            password_history: List of previous password hashes

        Returns:
            True if password is in history, False otherwise

        Example:
            >>> pm = PasswordManager()
            >>> old_hash = pm.hash_password("OldPassword123!")
            >>> pm.is_password_in_history("OldPassword123!", [old_hash])
            True

        ISO 27001: A.9.4.3 (Password history enforcement)
        """
        for old_hash in password_history[:self.policy.password_history_count]:
            if self.verify_password(new_password, old_hash):
                logger.info("Password found in history")
                return True

        return False

    def calculate_password_strength(self, password: str) -> dict:
        """
        Calculate password strength metrics.

        Args:
            password: Password to analyze

        Returns:
            Dictionary with strength metrics

        Example:
            >>> pm = PasswordManager()
            >>> metrics = pm.calculate_password_strength("SecureP@ssw0rd2025!")
            >>> metrics['score'] >= 4
            True
            >>> metrics['strength']
            'strong'
        """
        score = 0
        feedback = []

        # Length scoring
        if len(password) >= 16:
            score += 2
            feedback.append("Excellent length")
        elif len(password) >= 12:
            score += 1
            feedback.append("Good length")
        else:
            feedback.append("Consider longer password")

        # Character diversity
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)

        diversity = sum([has_upper, has_lower, has_digit, has_special])
        score += diversity

        if diversity == 4:
            feedback.append("Excellent character diversity")
        elif diversity >= 3:
            feedback.append("Good character diversity")
        else:
            feedback.append("Increase character diversity")

        # Entropy estimation (bits)
        charset_size = 0
        if has_upper:
            charset_size += 26
        if has_lower:
            charset_size += 26
        if has_digit:
            charset_size += 10
        if has_special:
            charset_size += 20

        import math
        entropy = len(password) * math.log2(charset_size) if charset_size > 0 else 0

        if entropy >= 80:
            score += 2
            feedback.append("High entropy")
        elif entropy >= 60:
            score += 1
            feedback.append("Moderate entropy")

        # Determine strength level
        if score >= 7:
            strength = "very strong"
        elif score >= 5:
            strength = "strong"
        elif score >= 3:
            strength = "moderate"
        elif score >= 1:
            strength = "weak"
        else:
            strength = "very weak"

        return {
            "score": score,
            "max_score": 9,
            "strength": strength,
            "entropy_bits": round(entropy, 2),
            "feedback": feedback,
            "character_types": {
                "uppercase": has_upper,
                "lowercase": has_lower,
                "digit": has_digit,
                "special": has_special,
            },
        }
