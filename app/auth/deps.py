from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.jwt import decode_token
from app.db import get_db
from app.models.user import User, UserRole, UserStatus


security = HTTPBearer(auto_error=False)


def get_user_by_id(conn, user_id: int) -> Optional[dict]:
    cursor = conn.execute(
        "SELECT * FROM users WHERE id = ? AND is_active = 1 AND status = ?",
        (user_id, UserStatus.APPROVED.value)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    token = None

    if credentials:
        token = credentials.credentials
    else:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = int(payload["sub"])

    with get_db() as conn:
        user_data = get_user_by_id(conn, user_id)

    if not user_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return User(
        id=user_data["id"],
        email=user_data["email"],
        role=UserRole(user_data["role"]),
        is_active=bool(user_data["is_active"]),
        status=UserStatus(user_data["status"]),
        rejected_reason=user_data.get("rejected_reason"),
        created_at=user_data["created_at"],
        updated_at=user_data["updated_at"],
    )


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    try:
        return await get_current_user(request, credentials)
    except HTTPException:
        return None


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
