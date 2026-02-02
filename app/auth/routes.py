from datetime import datetime, timezone, timedelta
from typing import Optional
import secrets

from fastapi import APIRouter, Depends, HTTPException, status, Response, Cookie, Form, Request
from pydantic import BaseModel, EmailStr

from app.db import get_db
from app.auth.hashing import verify_password, hash_token, hash_password
from app.crypto import encrypt_token, decrypt_token
from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.deps import get_current_user
from app.models.user import User, UserStatus


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"email": "user@example.com", "password": "your-password"}
            ]
        }
    }


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"access_token": "eyJhbGciOi...", "token_type": "bearer", "expires_in": 900}
            ]
        }
    }


class RefreshRequest(BaseModel):
    refresh_token: str
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"refresh_token": "refresh-token-value"}
            ]
        }
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"current_password": "old-pass", "new_password": "new-pass"}
            ]
        }
    }


class PersonalTokenRequest(BaseModel):
    name: Optional[str] = None
    expires_days: int = 30
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"name": "gpt", "expires_days": 30}
            ]
        }
    }


class ClientCredentialsRequest(BaseModel):
    client_id: str
    client_secret: str
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"client_id": "client_123", "client_secret": "secret_abc"}
            ]
        }
    }


class ClientCredentialsCreateRequest(BaseModel):
    name: Optional[str] = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"name": "chatgpt"}
            ]
        }
    }


def get_user_by_email(conn, email: str) -> Optional[dict]:
    cursor = conn.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1",
        (email,)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def save_refresh_token(conn, user_id: int, token: str, expires_at: datetime):
    token_hash = hash_token(token)
    conn.execute(
        """INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
           VALUES (?, ?, ?)""",
        (user_id, token_hash, expires_at.isoformat())
    )
    conn.commit()


def get_valid_refresh_token(conn, token: str) -> Optional[dict]:
    token_hash = hash_token(token)
    cursor = conn.execute(
        """SELECT rt.*, u.email, u.role FROM refresh_tokens rt
           JOIN users u ON rt.user_id = u.id
           WHERE rt.token_hash = ?
             AND rt.revoked_at IS NULL
             AND rt.expires_at > ?
             AND u.is_active = 1
             AND u.status = ?""",
        (token_hash, datetime.now(timezone.utc).isoformat(), UserStatus.APPROVED.value)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def revoke_refresh_token(conn, token: str):
    token_hash = hash_token(token)
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at = ? WHERE token_hash = ?",
        (datetime.now(timezone.utc).isoformat(), token_hash)
    )
    conn.commit()


def revoke_all_user_tokens(conn, user_id: int):
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL",
        (datetime.now(timezone.utc).isoformat(), user_id)
    )
    conn.commit()


@router.post(
    "/login",
    response_model=TokenResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "login_success": {
                            "summary": "Login success",
                            "value": {
                                "access_token": "eyJhbGciOi...",
                                "token_type": "bearer",
                                "expires_in": 900,
                            },
                        }
                    }
                }
            }
        }
    },
)
async def login(data: LoginRequest, response: Response):
    with get_db() as conn:
        user = get_user_by_email(conn, data.email)

        if not user or not verify_password(data.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        if user.get("status") == UserStatus.PENDING.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Signup request is pending approval",
            )

        if user.get("status") == UserStatus.REJECTED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Signup request was rejected",
            )

        access_token = create_access_token(
            user_id=user["id"],
            email=user["email"],
            role=user["role"]
        )

        refresh_token, refresh_expires = create_refresh_token()
        save_refresh_token(conn, user["id"], refresh_token, refresh_expires)

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60  # 7 days
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=30 * 24 * 60 * 60
        )

        return TokenResponse(
            access_token=access_token,
            expires_in=7 * 24 * 60 * 60  # 7 days
        )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "refresh_success": {
                            "summary": "Refresh success",
                            "value": {
                                "access_token": "eyJhbGciOi...",
                                "token_type": "bearer",
                                "expires_in": 900,
                            },
                        }
                    }
                }
            }
        }
    },
)
async def refresh(
    response: Response,
    data: Optional[RefreshRequest] = None,
    refresh_token: Optional[str] = Cookie(None)
):
    token = data.refresh_token if data else refresh_token

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required"
        )

    with get_db() as conn:
        token_data = get_valid_refresh_token(conn, token)

        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token"
            )

        revoke_refresh_token(conn, token)

        access_token = create_access_token(
            user_id=token_data["user_id"],
            email=token_data["email"],
            role=token_data["role"]
        )

        new_refresh_token, refresh_expires = create_refresh_token()
        save_refresh_token(conn, token_data["user_id"], new_refresh_token, refresh_expires)

        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=7 * 24 * 60 * 60  # 7 days
        )
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=30 * 24 * 60 * 60
        )

        return TokenResponse(
            access_token=access_token,
            expires_in=7 * 24 * 60 * 60  # 7 days
        )


@router.post(
    "/logout",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "logout": {"summary": "Logout", "value": {"message": "Logged out successfully"}}
                    }
                }
            }
        }
    },
)
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    refresh_token: Optional[str] = Cookie(None)
):
    with get_db() as conn:
        if refresh_token:
            revoke_refresh_token(conn, refresh_token)
        else:
            revoke_all_user_tokens(conn, current_user.id)

    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")

    return {"message": "Logged out successfully"}


@router.get(
    "/me",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "me": {
                            "summary": "Current user",
                            "value": {
                                "id": 1,
                                "email": "user@example.com",
                                "role": "user",
                                "is_active": True,
                                "status": "approved",
                            },
                        }
                    }
                }
            }
        }
    },
)
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "role": current_user.role,
        "is_active": current_user.is_active,
        "status": current_user.status,
    }


@router.post(
    "/change_password",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "password_changed": {
                            "summary": "Password changed",
                            "value": {"message": "Password updated"},
                        }
                    }
                }
            }
        }
    },
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1",
            (current_user.id,),
        )
        row = cursor.fetchone()
        if not row or not verify_password(data.current_password, row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        password_hash = hash_password(data.new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = datetime('now') WHERE id = ?",
            (password_hash, current_user.id),
        )
        revoke_all_user_tokens(conn, current_user.id)
        conn.commit()

    return {"message": "Password updated"}


@router.post(
    "/personal_token",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "pat": {
                            "summary": "Personal access token",
                            "value": {
                                "token": "pat_xxxxxxxxxxxxxxxxx",
                                "expires_at": "2026-03-03T10:00:00+00:00",
                            },
                        }
                    }
                }
            }
        }
    },
)
async def create_personal_token(
    data: PersonalTokenRequest,
    current_user: User = Depends(get_current_user),
):
    if data.expires_days < 30 or data.expires_days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="expires_days must be between 30 and 365",
        )

    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_days)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO personal_access_tokens (user_id, token_hash, name, expires_at)
               VALUES (?, ?, ?, ?)""",
            (current_user.id, token_hash, data.name, expires_at.isoformat()),
        )
        conn.commit()

    return {"token": raw_token, "expires_at": expires_at.isoformat()}


@router.post(
    "/client_token",
    response_model=TokenResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "client_token": {
                            "summary": "Client credentials token",
                            "value": {
                                "access_token": "eyJhbGciOi...",
                                "token_type": "bearer",
                                "expires_in": 900,
                            },
                        }
                    }
                }
            }
        }
    },
)
async def client_token(data: ClientCredentialsRequest, response: Response):
    secret_hash = hash_token(data.client_secret)
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT c.user_id, u.email, u.role, u.status, u.is_active
               FROM api_clients c
               JOIN users u ON c.user_id = u.id
               WHERE c.client_id = ? AND c.client_secret_hash = ? AND c.is_active = 1""",
            (data.client_id, secret_hash),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid client credentials",
            )
        if not row["is_active"] or row["status"] != UserStatus.APPROVED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User is not approved or inactive",
            )

        conn.execute(
            "UPDATE api_clients SET last_used_at = ? WHERE client_id = ?",
            (datetime.now(timezone.utc).isoformat(), data.client_id),
        )
        conn.commit()

        access_token = create_access_token(
            user_id=row["user_id"],
            email=row["email"],
            role=row["role"],
        )

    return TokenResponse(access_token=access_token, expires_in=15 * 60)


@router.post(
    "/client_credentials",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "client_credentials": {
                            "summary": "Client credentials",
                            "value": {"client_id": "client_123", "client_secret": "secret_abc"},
                        }
                    }
                }
            }
        }
    },
)
async def create_client_credentials_for_user(
    data: ClientCredentialsCreateRequest,
    current_user: User = Depends(get_current_user),
):
    client_id = secrets.token_urlsafe(12)
    client_secret = secrets.token_urlsafe(24)
    client_secret_hash = hash_token(client_secret)
    client_secret_enc = encrypt_token(client_secret)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO api_clients (user_id, client_id, client_secret_hash, client_secret_enc, name)
               VALUES (?, ?, ?, ?, ?)""",
            (current_user.id, client_id, client_secret_hash, client_secret_enc, data.name),
        )
        conn.commit()

    return {"client_id": client_id, "client_secret": client_secret}


@router.get(
    "/client_credentials",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "list": {
                            "summary": "Credentials list",
                            "value": {
                                "items": [
                                    {
                                        "client_id": "client_123",
                                        "name": "chatgpt",
                                        "created_at": "2026-02-01T10:00:00",
                                        "last_used_at": "2026-02-01T12:00:00",
                                        "has_secret": True,
                                    }
                                ]
                            },
                        }
                    }
                }
            }
        }
    },
)
async def list_client_credentials(current_user: User = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT client_id, name, created_at, last_used_at, client_secret_enc
               FROM api_clients WHERE user_id = ? AND is_active = 1
               ORDER BY created_at DESC""",
            (current_user.id,),
        )
        results = []
        for row in cursor.fetchall():
            results.append(
                {
                    "client_id": row["client_id"],
                    "name": row["name"],
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                    "has_secret": bool(row["client_secret_enc"]),
                }
            )
        return {"items": results}


@router.get(
    "/client_credentials/{client_id}",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "reveal": {
                            "summary": "Reveal secret",
                            "value": {"client_id": "client_123", "client_secret": "secret_abc"},
                        }
                    }
                }
            }
        }
    },
)
async def reveal_client_credentials(
    client_id: str,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT client_secret_enc FROM api_clients
               WHERE user_id = ? AND client_id = ? AND is_active = 1""",
            (current_user.id, client_id),
        )
        row = cursor.fetchone()
        if not row or not row["client_secret_enc"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Secret not available")
        return {"client_id": client_id, "client_secret": decrypt_token(row["client_secret_enc"])}


@router.delete(
    "/client_credentials/{client_id}",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "delete": {"summary": "Deleted", "value": {"deleted": True}}
                    }
                }
            }
        }
    },
)
async def delete_client_credentials(
    client_id: str,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM api_clients WHERE user_id = ? AND client_id = ?",
            (current_user.id, client_id),
        )
        conn.commit()
    return {"deleted": True}


oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])


@oauth_router.post(
    "/token",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "oauth_token": {
                            "summary": "OAuth client_credentials",
                            "value": {
                                "access_token": "eyJhbGciOi...",
                                "token_type": "bearer",
                                "expires_in": 900,
                            },
                        }
                    }
                }
            }
        }
    },
)
async def oauth_token(
    request: Request,
    grant_type: Optional[str] = Form(None),
    client_id: Optional[str] = Form(None),
    client_secret: Optional[str] = Form(None),
    code: Optional[str] = Form(None),
    redirect_uri: Optional[str] = Form(None),
    code_verifier: Optional[str] = Form(None),
):
    # Support both form and JSON
    if grant_type is None:
        try:
            data = await request.json()
            grant_type = data.get("grant_type")
            client_id = data.get("client_id")
            client_secret = data.get("client_secret")
            code = data.get("code")
            redirect_uri = data.get("redirect_uri")
            code_verifier = data.get("code_verifier")
        except Exception:
            pass

    print(f"[OAUTH] Token request: grant_type={grant_type}")

    # Handle authorization_code grant (for ChatGPT/MCP clients)
    if grant_type == "authorization_code":
        from app.mcp_gateway.oauth_server import _auth_codes, _verify_pkce
        from fastapi.responses import JSONResponse
        import time

        if not code:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Missing code"},
                status_code=400
            )

        # Get and remove auth code (one-time use)
        auth_data = _auth_codes.pop(code, None)
        if not auth_data:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Invalid or expired code"},
                status_code=400
            )

        # Check code expiration (10 minutes)
        if time.time() - auth_data["created_at"] > 600:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Code expired"},
                status_code=400
            )

        # Verify redirect_uri matches
        if redirect_uri and redirect_uri != auth_data["redirect_uri"]:
            return JSONResponse(
                {"error": "invalid_grant", "error_description": "Redirect URI mismatch"},
                status_code=400
            )

        # Verify PKCE if it was used
        if auth_data["code_challenge"]:
            if not code_verifier:
                return JSONResponse(
                    {"error": "invalid_request", "error_description": "Missing code_verifier"},
                    status_code=400
                )

            method = auth_data["code_challenge_method"] or "S256"
            if not _verify_pkce(code_verifier, auth_data["code_challenge"], method):
                return JSONResponse(
                    {"error": "invalid_grant", "error_description": "Invalid code_verifier"},
                    status_code=400
                )

        # Generate access token (JWT)
        access_token = create_access_token(
            user_id=auth_data["user_id"],
            email=auth_data["user_email"],
            role=auth_data["user_role"],
        )

        print(f"[OAUTH] Token issued for user {auth_data['user_email']}")

        return JSONResponse(
            content={
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": 20 * 24 * 60 * 60,  # 20 days in seconds
                "scope": auth_data["scope"] or "mcp",
            },
            headers={"Cache-Control": "no-store"},
        )

    # Handle client_credentials grant (for API keys)
    if grant_type == "client_credentials":
        if not client_id or not client_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="client_id and client_secret are required",
            )

        return await client_token(
            ClientCredentialsRequest(client_id=client_id, client_secret=client_secret),
            Response(),
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported grant_type: {grant_type}",
    )
