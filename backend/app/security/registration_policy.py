"""Who may create an account — PRB-020 (REQ-SEC-030, REQ-SEC-031; HAZ-010).

THE DEFECT THIS CLOSES
----------------------
`POST /api/v1/auth/register` was public: anyone who could reach the server created a VIEWER account,
with no e-mail verification, and the sign-in page offered a "Register" tab. A VIEWER could then read
the whole patient registry (PRB-021). For a device that is not CE-marked, offering it to any clinician
who signs up — even free of charge — can count as "making available" under EU MDR arts. 2(27) and 6.

THE RULE
--------
Accounts are created by an administrator (`POST /api/v1/auth/users`). Self-registration is OFF unless
the setting SELF_REGISTRATION_ENABLED is true AND ENVIRONMENT is one of development, local, test, testing;
any other ENVIRONMENT (production, prod, staging, empty...) counts as production, so it is never on there,
whatever the setting says: that combination needs a code change, a code review and the owner's
regulatory decision. When it is off the register route answers 404, as if it did not exist, before the
request body is used; the sign-in page asks `GET /api/v1/auth/registration` and hides the tab.
"""
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

PRODUCTION = "production"
# Review of PR #70, m4 — fail closed: only these ENVIRONMENT values count as non-production. Any other value
# ("prod", "staging", "live", empty, a typo) is treated as production, so a production service configured with a
# different spelling can never open self-registration.
NON_PRODUCTION_ENVIRONMENTS = frozenset({"development", "local", "test", "testing"})


def is_non_production(environment) -> bool:
    return str(environment if environment is not None else PRODUCTION).strip().lower() in NON_PRODUCTION_ENVIRONMENTS


def self_registration_enabled() -> bool:
    """True only when the setting is on AND the server is explicitly a non-production server.

    Read at call time (not at import), so a change of configuration takes effect without a code path
    that caches an old answer."""
    settings = get_settings()
    requested = bool(getattr(settings, "SELF_REGISTRATION_ENABLED", False))
    if not requested:
        return False
    if not is_non_production(getattr(settings, "ENVIRONMENT", PRODUCTION)):
        logger.warning(
            "SELF_REGISTRATION_ENABLED is set on a production server and is ignored (PRB-020)",
            extra={"setting": "SELF_REGISTRATION_ENABLED"},
        )
        return False
    return True


async def require_self_registration_enabled() -> None:
    """FastAPI dependency of the register route: 404 when self-registration is off.

    `async def` on purpose (CAPA-009: a plain-def dependency returning a coroutine was never awaited)."""
    if not self_registration_enabled():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not Found",
        )


def registration_status() -> dict:
    """The public answer of GET /api/v1/auth/registration (no secret, no account data)."""
    enabled = self_registration_enabled()
    return {"self_registration_enabled": enabled, "account_creation": "self" if enabled else "administrator"}
