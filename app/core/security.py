from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.repositories.user_repository import get_user_by_id


password_hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)
INVALID_CREDENTIALS_MESSAGE = "Invalid email or password"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, plain_password)
    except (InvalidHashError, VerificationError, VerifyMismatchError, TypeError):
        return False


def _jwt_signing_key() -> str:
    configured_key = settings.JWT_SECRET_KEY
    if isinstance(configured_key, SecretStr):
        configured_key = configured_key.get_secret_value()
    if not isinstance(configured_key, str) or len(configured_key.encode()) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be configured with at least 32 characters"
        )
    return configured_key


def create_access_token(
    user_id: int,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    lifetime = expires_delta or timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expires_at = now + lifetime
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(
        payload,
        _jwt_signing_key(),
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(
        token,
        _jwt_signing_key(),
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "iat", "exp"]},
    )
    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise jwt.InvalidTokenError("Token subject must be a string")
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise jwt.InvalidTokenError("Token subject must be a numeric user ID") from exc
    if user_id <= 0 or str(user_id) != subject:
        raise jwt.InvalidTokenError("Token subject must be a positive numeric user ID")
    return payload


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _authentication_error()

    try:
        payload = verify_access_token(credentials.credentials)
        user_id = int(payload["sub"])
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise _authentication_error() from None

    user = get_user_by_id(db, user_id)
    if user is None:
        raise _authentication_error()
    return user


def require_roles(*allowed_roles: str) -> Callable[..., User]:
    if not allowed_roles:
        raise ValueError("At least one allowed role is required")

    def role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return current_user

    return role_dependency
