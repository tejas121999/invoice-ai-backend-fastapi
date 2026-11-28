from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    INVALID_CREDENTIALS_MESSAGE,
    create_access_token,
    verify_password,
)
from app.repositories.user_repository import get_user_by_email


def authenticate_user(db: Session, email: str, password: str) -> dict[str, object]:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.passwordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_MESSAGE,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "expires_in": settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }
