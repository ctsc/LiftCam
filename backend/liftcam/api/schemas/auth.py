from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from liftcam.core.identity import is_at_least_age


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class SignupRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    dob: date
    height: float = Field(gt=0)
    height_unit: Literal["in", "cm"] = "in"
    weight: float = Field(gt=0)
    weight_unit: Literal["lb", "kg"] = "lb"
    sex: Literal["male", "female"]
    squat_max: float = Field(gt=0)
    bench_max: float = Field(gt=0)
    deadlift_max: float = Field(gt=0)
    profile_picture_url: str | None = Field(default=None, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("username must be at least 3 characters")
        return cleaned

    @field_validator("dob")
    @classmethod
    def require_age_13(cls, value: date) -> date:
        if not is_at_least_age(value, 13):
            raise ValueError("You must be at least 13 years old to create an account")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    auth_provider: str
    dob: date
    height: float
    height_unit: str
    weight: float
    weight_unit: str
    sex: str
    squat_max: float
    bench_max: float
    deadlift_max: float
    favorite_lift: str | None
    profile_picture_url: str
    tier: str
    created_at: datetime


class ProfileUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=64)
    dob: date | None = None
    height: float | None = Field(default=None, gt=0)
    height_unit: Literal["in", "cm"] | None = None
    weight: float | None = Field(default=None, gt=0)
    weight_unit: Literal["lb", "kg"] | None = None
    sex: Literal["male", "female"] | None = None
    squat_max: float | None = Field(default=None, gt=0)
    bench_max: float | None = Field(default=None, gt=0)
    deadlift_max: float | None = Field(default=None, gt=0)
    favorite_lift: str | None = Field(default=None, max_length=32)
    profile_picture_url: str | None = Field(default=None, max_length=1024)

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 3:
            raise ValueError("username must be at least 3 characters")
        return cleaned

    @field_validator("dob")
    @classmethod
    def require_age_13(cls, value: date | None) -> date | None:
        if value is not None and not is_at_least_age(value, 13):
            raise ValueError("You must be at least 13 years old to create an account")
        return value


class PushTokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=512)
