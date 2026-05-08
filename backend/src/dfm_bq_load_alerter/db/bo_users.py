"""bo_users 테이블 upsert 헬퍼."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.db.models import BOUser, UserRole


async def upsert_login(
    session: AsyncSession,
    *,
    keycloak_subject: str,
    email: str | None,
) -> BOUser:
    now = datetime.now(UTC)
    result = await session.execute(
        select(BOUser).where(BOUser.keycloak_subject == keycloak_subject)
    )
    user = result.scalar_one_or_none()
    if user is None:
        user = BOUser(
            keycloak_subject=keycloak_subject,
            email=email,
            role=UserRole.viewer,
            last_login=now,
        )
        session.add(user)
    else:
        if email is not None and user.email != email:
            user.email = email
        user.last_login = now
    await session.commit()
    await session.refresh(user)
    return user
