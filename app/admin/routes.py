from datetime import datetime, timezone
from typing import Optional
import secrets
import json

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr

from app.db import get_db
from app.auth.deps import require_admin
from app.auth.hashing import hash_password, hash_token
from app.crypto import encrypt_token
from app.models.user import User, UserRole, UserStatus
from app.config.store import (
    PUBLIC_BASE_URL_KEY,
    PUBLIC_HOST_KEY,
    TEAMWORK_CLIENT_ID_KEY,
    TEAMWORK_CLIENT_SECRET_KEY,
    SLACK_CLIENT_ID_KEY,
    SLACK_CLIENT_SECRET_KEY,
    MIRO_CLIENT_ID_KEY,
    MIRO_CLIENT_SECRET_KEY,
    TELEGRAM_API_ID_KEY,
    TELEGRAM_API_HASH_KEY,
    get_setting,
    set_setting,
)
from app.integrations.connections import get_user_connections


router = APIRouter(prefix="/api/admin", tags=["admin"])


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.USER
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"email": "newuser@example.com", "password": "password", "role": "user"}
            ]
        }
    }


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    status: Optional[UserStatus] = None
    rejected_reason: Optional[str] = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"role": "admin", "is_active": True},
                {"status": "rejected", "rejected_reason": "Not approved yet"},
            ]
        }
    }


class UserResponse(BaseModel):
    id: int
    email: str
    role: UserRole
    is_active: bool
    status: UserStatus
    rejected_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    connections: list[str] = []
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "email": "user@example.com",
                    "role": "user",
                    "is_active": True,
                    "status": "approved",
                    "rejected_reason": None,
                    "created_at": "2026-02-01T10:00:00",
                    "updated_at": "2026-02-01T10:00:00",
                    "connections": ["telegram"],
                }
            ]
        }
    }


class ClientCredentialsResponse(BaseModel):
    client_id: str
    client_secret: str


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int]
    user_email: Optional[str]
    provider: Optional[str]
    action: str
    status: str
    error_text: Optional[str]
    created_at: datetime


class AdminSettingsResponse(BaseModel):
    public_base_url: Optional[str] = None
    public_host: Optional[str] = None
    teamwork_client_id: Optional[str] = None
    teamwork_client_secret: Optional[str] = None
    slack_client_id: Optional[str] = None
    slack_client_secret: Optional[str] = None
    miro_client_id: Optional[str] = None
    miro_client_secret: Optional[str] = None
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None


class AdminSettingsUpdate(BaseModel):
    public_base_url: Optional[str] = None
    public_host: Optional[str] = None
    teamwork_client_id: Optional[str] = None
    teamwork_client_secret: Optional[str] = None
    slack_client_id: Optional[str] = None
    slack_client_secret: Optional[str] = None
    miro_client_id: Optional[str] = None
    miro_client_secret: Optional[str] = None
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "public_base_url": "https://mcp.example.com",
                    "teamwork_client_id": "tw_client_id",
                    "teamwork_client_secret": "tw_secret",
                    "slack_client_id": "slack_client_id",
                    "slack_client_secret": "slack_secret",
                    "miro_client_id": "miro_client_id",
                    "miro_client_secret": "miro_secret",
                    "telegram_api_id": "123456",
                    "telegram_api_hash": "hash",
                }
            ]
        }
    }


def row_to_user_response(row: dict, connections: Optional[list[str]] = None) -> UserResponse:
    return UserResponse(
        id=row["id"],
        email=row["email"],
        role=UserRole(row["role"]),
        is_active=bool(row["is_active"]),
        status=UserStatus(row["status"]),
        rejected_reason=row.get("rejected_reason"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        connections=connections or [],
    )


@router.get(
    "/users",
    response_model=list[UserResponse],
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "users": {
                            "summary": "Users list",
                            "value": [
                                {
                                    "id": 1,
                                    "email": "user@example.com",
                                    "role": "user",
                                    "is_active": True,
                                    "status": "approved",
                                    "rejected_reason": None,
                                    "created_at": "2026-02-01T10:00:00",
                                    "updated_at": "2026-02-01T10:00:00",
                                    "connections": ["telegram"],
                                }
                            ],
                        }
                    }
                }
            }
        }
    },
)
async def list_users(admin: User = Depends(require_admin)):
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        )
        users = [dict(row) for row in cursor.fetchall()]

        connections_by_user: dict[int, list[str]] = {}
        for user in users:
            connections = get_user_connections(conn, user["id"])
            connections_by_user[user["id"]] = list(connections.keys())

        result = []
        for user in users:
            conns = connections_by_user.get(user["id"], []) if user_ids else []
            result.append(row_to_user_response(user, conns))

        return result


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {
            "content": {
                "application/json": {
                    "examples": {
                        "created": {
                            "summary": "User created",
                            "value": {
                                "id": 2,
                                "email": "newuser@example.com",
                                "role": "user",
                                "is_active": True,
                                "status": "approved",
                                "rejected_reason": None,
                                "created_at": "2026-02-01T10:00:00",
                                "updated_at": "2026-02-01T10:00:00",
                                "connections": [],
                            },
                        }
                    }
                }
            }
        }
    },
)
async def create_user(
    data: UserCreateRequest,
    admin: User = Depends(require_admin),
):
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (data.email,)
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User with this email already exists"
            )

        password_hash = hash_password(data.password)
        cursor = conn.execute(
            """INSERT INTO users (email, password_hash, role, status)
               VALUES (?, ?, ?, ?)""",
            (data.email, password_hash, data.role.value, UserStatus.APPROVED.value)
        )
        conn.commit()
        user_id = cursor.lastrowid

        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cursor.fetchone())

        return row_to_user_response(user)


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "updated": {
                            "summary": "User updated",
                            "value": {
                                "id": 1,
                                "email": "user@example.com",
                                "role": "admin",
                                "is_active": True,
                                "status": "approved",
                                "rejected_reason": None,
                                "created_at": "2026-02-01T10:00:00",
                                "updated_at": "2026-02-01T10:00:00",
                                "connections": ["telegram"],
                            },
                        }
                    }
                }
            }
        }
    },
)
async def update_user(
    user_id: int,
    data: UserUpdateRequest,
    admin: User = Depends(require_admin),
):
    if user_id == admin.id and data.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )

    if user_id == admin.id and data.role == UserRole.USER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote your own account"
        )

    if user_id == admin.id and data.status in {UserStatus.PENDING, UserStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own approval status"
        )

    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        updates = []
        values = []

        if data.email is not None:
            cursor = conn.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?",
                (data.email, user_id)
            )
            if cursor.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )
            updates.append("email = ?")
            values.append(data.email)

        if data.role is not None:
            updates.append("role = ?")
            values.append(data.role.value)

        if data.is_active is not None:
            updates.append("is_active = ?")
            values.append(1 if data.is_active else 0)

        if data.status is not None:
            updates.append("status = ?")
            values.append(data.status.value)

        if data.rejected_reason is not None:
            updates.append("rejected_reason = ?")
            values.append(data.rejected_reason)

        if updates:
            updates.append("updated_at = datetime('now')")
            values.append(user_id)
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                values
            )
            conn.commit()

        cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = dict(cursor.fetchone())

        connections = list(get_user_connections(conn, user_id).keys())

        return row_to_user_response(user, connections)


@router.post(
    "/users/{user_id}/reset_password",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "reset": {
                            "summary": "Password reset",
                            "value": {"new_password": "temporary-pass"},
                        }
                    }
                }
            }
        }
    },
)
async def reset_user_password(
    user_id: int,
    admin: User = Depends(require_admin),
):
    with get_db() as conn:
        cursor = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        new_password = secrets.token_urlsafe(12)
        password_hash = hash_password(new_password)

        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (password_hash, user_id)
        )
        conn.execute(
            "UPDATE refresh_tokens SET revoked_at = datetime('now') WHERE user_id = ? AND revoked_at IS NULL",
            (user_id,)
        )
        conn.commit()

        return {"new_password": new_password}


@router.post(
    "/users/{user_id}/client_credentials",
    response_model=ClientCredentialsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "client_creds": {
                            "summary": "Client credentials",
                            "value": {"client_id": "client_123", "client_secret": "secret_abc"},
                        }
                    }
                }
            }
        }
    },
)
async def create_client_credentials(
    user_id: int,
    admin: User = Depends(require_admin),
):
    with get_db() as conn:
        cursor = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        client_id = secrets.token_urlsafe(12)
        client_secret = secrets.token_urlsafe(24)
        client_secret_hash = hash_token(client_secret)
        client_secret_enc = encrypt_token(client_secret)

        conn.execute(
            """INSERT INTO api_clients (user_id, client_id, client_secret_hash, client_secret_enc)
               VALUES (?, ?, ?, ?)""",
            (user_id, client_id, client_secret_hash, client_secret_enc)
        )
        conn.commit()

        return ClientCredentialsResponse(
            client_id=client_id,
            client_secret=client_secret
        )


@router.get(
    "/audit",
    response_model=list[AuditLogResponse],
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "logs": {
                            "summary": "Audit logs",
                            "value": [
                                {
                                    "id": 1,
                                    "user_id": 1,
                                    "user_email": "user@example.com",
                                    "provider": "telegram",
                                    "action": "telegram.messages.send",
                                    "status": "ok",
                                    "error_text": None,
                                    "created_at": "2026-02-01T10:00:00",
                                }
                            ],
                        }
                    }
                }
            }
        }
    },
)
async def list_audit_logs(
    admin: User = Depends(require_admin),
    user_id: Optional[int] = Query(None),
    provider: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
):
    with get_db() as conn:
        query = """
            SELECT a.*, u.email as user_email
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE 1=1
        """
        params: list = []

        if user_id is not None:
            query += " AND a.user_id = ?"
            params.append(user_id)

        if provider:
            query += " AND a.provider = ?"
            params.append(provider)

        if date_from:
            query += " AND a.created_at >= ?"
            params.append(date_from)

        if date_to:
            query += " AND a.created_at <= ?"
            params.append(date_to)

        query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        logs = []
        for row in cursor.fetchall():
            logs.append(AuditLogResponse(
                id=row["id"],
                user_id=row["user_id"],
                user_email=row["user_email"],
                provider=row["provider"],
                action=row["action"],
                status=row["status"],
                error_text=row["error_text"],
                created_at=row["created_at"],
            ))

        return logs


@router.get(
    "/settings",
    response_model=AdminSettingsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "settings": {
                            "summary": "Current settings",
                            "value": {
                                "public_base_url": "https://mcp.example.com",
                                "public_host": "mcp.example.com",
                                "teamwork_client_id": "tw_id",
                                "teamwork_client_secret": "tw_secret",
                                "slack_client_id": "slack_id",
                                "slack_client_secret": "slack_secret",
                                "miro_client_id": "miro_id",
                                "miro_client_secret": "miro_secret",
                                "telegram_api_id": "123456",
                                "telegram_api_hash": "hash",
                            },
                        }
                    }
                }
            }
        }
    },
)
async def get_admin_settings(admin: User = Depends(require_admin)):
    with get_db() as conn:
        return AdminSettingsResponse(
            public_base_url=get_setting(conn, PUBLIC_BASE_URL_KEY),
            public_host=get_setting(conn, PUBLIC_HOST_KEY),
            teamwork_client_id=get_setting(conn, TEAMWORK_CLIENT_ID_KEY),
            teamwork_client_secret=get_setting(conn, TEAMWORK_CLIENT_SECRET_KEY),
            slack_client_id=get_setting(conn, SLACK_CLIENT_ID_KEY),
            slack_client_secret=get_setting(conn, SLACK_CLIENT_SECRET_KEY),
            miro_client_id=get_setting(conn, MIRO_CLIENT_ID_KEY),
            miro_client_secret=get_setting(conn, MIRO_CLIENT_SECRET_KEY),
            telegram_api_id=get_setting(conn, TELEGRAM_API_ID_KEY),
            telegram_api_hash=get_setting(conn, TELEGRAM_API_HASH_KEY),
        )


@router.put(
    "/settings",
    response_model=AdminSettingsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "updated": {
                            "summary": "Updated settings",
                            "value": {
                                "public_base_url": "https://mcp.example.com",
                                "public_host": "mcp.example.com",
                                "teamwork_client_id": "tw_id",
                                "teamwork_client_secret": "tw_secret",
                                "slack_client_id": "slack_id",
                                "slack_client_secret": "slack_secret",
                                "miro_client_id": "miro_id",
                                "miro_client_secret": "miro_secret",
                                "telegram_api_id": "123456",
                                "telegram_api_hash": "hash",
                            },
                        }
                    }
                }
            }
        }
    },
)
async def update_admin_settings(
    data: AdminSettingsUpdate,
    admin: User = Depends(require_admin),
):
    with get_db() as conn:
        set_setting(conn, PUBLIC_BASE_URL_KEY, data.public_base_url)
        set_setting(conn, PUBLIC_HOST_KEY, data.public_host)
        set_setting(conn, TEAMWORK_CLIENT_ID_KEY, data.teamwork_client_id)
        set_setting(conn, TEAMWORK_CLIENT_SECRET_KEY, data.teamwork_client_secret)
        set_setting(conn, SLACK_CLIENT_ID_KEY, data.slack_client_id)
        set_setting(conn, SLACK_CLIENT_SECRET_KEY, data.slack_client_secret)
        set_setting(conn, MIRO_CLIENT_ID_KEY, data.miro_client_id)
        set_setting(conn, MIRO_CLIENT_SECRET_KEY, data.miro_client_secret)
        set_setting(conn, TELEGRAM_API_ID_KEY, data.telegram_api_id)
        set_setting(conn, TELEGRAM_API_HASH_KEY, data.telegram_api_hash)

        return AdminSettingsResponse(
            public_base_url=get_setting(conn, PUBLIC_BASE_URL_KEY),
            public_host=get_setting(conn, PUBLIC_HOST_KEY),
            teamwork_client_id=get_setting(conn, TEAMWORK_CLIENT_ID_KEY),
            teamwork_client_secret=get_setting(conn, TEAMWORK_CLIENT_SECRET_KEY),
            slack_client_id=get_setting(conn, SLACK_CLIENT_ID_KEY),
            slack_client_secret=get_setting(conn, SLACK_CLIENT_SECRET_KEY),
            miro_client_id=get_setting(conn, MIRO_CLIENT_ID_KEY),
            miro_client_secret=get_setting(conn, MIRO_CLIENT_SECRET_KEY),
            telegram_api_id=get_setting(conn, TELEGRAM_API_ID_KEY),
            telegram_api_hash=get_setting(conn, TELEGRAM_API_HASH_KEY),
        )
