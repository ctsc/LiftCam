"""Profile routes: /me and push token registration."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.exc import IntegrityError

from liftcam.api.deps import CurrentUser, DbSession
from liftcam.api.schemas import MeOut, ProfileUpdateRequest, PushTokenRequest

router = APIRouter(tags=["users"])


@router.get("/me", response_model=MeOut)
async def get_me(user: CurrentUser) -> MeOut:
    return MeOut.model_validate(user)


@router.patch("/me", response_model=MeOut)
async def patch_me(
    body: ProfileUpdateRequest,
    user: CurrentUser,
    session: DbSession,
) -> MeOut:
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(user, key, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already in use",
        ) from exc
    await session.refresh(user)
    return MeOut.model_validate(user)


@router.post("/me/push-token", status_code=status.HTTP_204_NO_CONTENT)
async def set_push_token(
    body: PushTokenRequest,
    user: CurrentUser,
    session: DbSession,
) -> None:
    user.expo_push_token = body.token
    await session.commit()
