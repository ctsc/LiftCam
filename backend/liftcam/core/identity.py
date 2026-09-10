"""Age gate and provider-agnostic user lookup (email today; Apple/Google in Phase 19)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from liftcam.core.models import User


def is_at_least_age(dob: date, min_age: int, *, today: date | None = None) -> bool:
    """True when the person has already reached `min_age` on `today` (inclusive)."""
    if min_age < 0:
        raise ValueError("min_age must be non-negative")
    as_of = today or date.today()
    try:
        birthday = dob.replace(year=dob.year + min_age)
    except ValueError:
        # Feb 29 → treat birthday as March 1 in non-leap years.
        birthday = date(dob.year + min_age, 3, 1)
    return as_of >= birthday


def _identity_stmt(*, email: str | None, apple_user_id: str | None) -> Select[tuple[User]]:
    if email is None and apple_user_id is None:
        raise ValueError("email or apple_user_id is required")
    stmt = select(User)
    if email is not None:
        return stmt.where(User.email == email.lower())
    return stmt.where(User.apple_user_id == apple_user_id)


async def find_user_by_verified_identity(
    session: AsyncSession,
    *,
    email: str | None = None,
    apple_user_id: str | None = None,
) -> User | None:
    """Resolve a user from a verified identity claim.

    Email is the primary dedup key across providers. Apple's private relay falls
    back to `apple_user_id`. Phase 19 OAuth routes call this same helper.
    """
    result = await session.execute(_identity_stmt(email=email, apple_user_id=apple_user_id))
    return result.scalar_one_or_none()
