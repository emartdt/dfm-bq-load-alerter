"""Temporary bootstrap-token authentication.

Active only while OIDC is not configured (PR-5 not yet merged). Replaced
by Keycloak verification in PR-5. Behaviour:

- If `settings.is_oidc_enabled` is True → 503 (caller must use OIDC; this
  guard refuses to operate to prevent silent fall-through).
- If bootstrap_token is empty → endpoint disabled (401).
- Otherwise compare `Authorization: Bearer <token>` against the configured
  bootstrap token in constant time.
"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request, status

from dfm_bq_load_alerter.settings import settings


def _extract_bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, value = header.partition(" ")
    if scheme.lower() != "bearer" or not value:
        return None
    return value.strip()


async def require_admin(request: Request) -> dict[str, str]:
    """Bootstrap-token guard. Returns a minimal principal dict on success."""
    if settings.is_oidc_enabled:
        # OIDC is configured but no OIDC verifier is wired yet — refuse to
        # silently fall through to bootstrap token in production.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is configured but PR-5 verifier is not yet active.",
        )

    if not settings.bootstrap_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is not configured (no bootstrap token, no OIDC).",
        )

    presented = _extract_bearer(request)
    if presented is None or not hmac.compare_digest(presented, settings.bootstrap_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bootstrap token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"role": "admin", "auth": "bootstrap"}
