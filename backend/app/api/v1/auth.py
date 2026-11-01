from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import ClientIP, CurrentUser, Database
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Database, ip_address: ClientIP) -> TokenResponse:
    return user_service.register_user(db, payload, ip_address)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Database, ip_address: ClientIP) -> TokenResponse:
    return user_service.login(db, payload.email, payload.password, ip_address)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(payload: ProfileUpdateRequest, db: Database, user: CurrentUser) -> UserOut:
    return user_service.update_profile(db, user, payload.full_name)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordRequest, db: Database, user: CurrentUser) -> Response:
    user_service.change_password(db, user, payload.current_password, payload.new_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
