import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from app.integrations.telegram import auth as telegram_auth

from app.db import get_db
from app.auth.deps import get_current_user
from app.models.user import User
from app.integrations.registry import integration_registry
from app.config.store import get_public_base_url
from app.integrations.connections import get_user_connections, save_connection, delete_connection
from app.mcp_gateway.audit import log_tool_call


router = APIRouter(prefix="/integrations", tags=["integrations"])
oauth_router = APIRouter(prefix="/oauth", tags=["oauth"])


def safe_audit_log(
    user_id: int,
    provider: Optional[str],
    action: str,
    request_data: Optional[dict],
    response_data: Optional[dict],
    status: str,
    error_text: Optional[str] = None,
):
    try:
        log_tool_call(
            user_id=user_id,
            provider=provider,
            action=action,
            request_data=request_data,
            response_data=response_data,
            status=status,
            error_text=error_text,
        )
    except Exception:
        pass


class IntegrationStatus(BaseModel):
    name: str
    display_name: str
    description: str
    is_configured: bool
    is_connected: bool
    connected_at: Optional[datetime] = None
    meta: Optional[dict] = None
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "telegram",
                    "display_name": "Telegram",
                    "description": "Telegram messaging via MTProto user session",
                    "is_configured": True,
                    "is_connected": True,
                    "connected_at": "2026-02-01T10:00:00",
                    "meta": {"telegram_user_id": 12345, "username": "example"},
                }
            ]
        }
    }


class TelegramStartRequest(BaseModel):
    phone: str
    model_config = {
        "json_schema_extra": {"examples": [{"phone": "+1234567890"}]}
    }


class TelegramVerifyRequest(BaseModel):
    login_id: str
    code: str
    model_config = {
        "json_schema_extra": {"examples": [{"login_id": "login_id", "code": "12345"}]}
    }


class TelegramPasswordRequest(BaseModel):
    login_id: str
    password: str
    model_config = {
        "json_schema_extra": {"examples": [{"login_id": "login_id", "password": "2fa-password"}]}
    }


def save_oauth_state(conn, state: str, user_id: int, provider: str):
    conn.execute(
        "DELETE FROM oauth_states WHERE user_id = ? AND provider = ?",
        (user_id, provider)
    )
    conn.execute(
        "INSERT INTO oauth_states (state, user_id, provider) VALUES (?, ?, ?)",
        (state, user_id, provider)
    )
    conn.commit()


def get_oauth_state(conn, state: str) -> Optional[dict]:
    cursor = conn.execute(
        """SELECT * FROM oauth_states
           WHERE state = ? AND created_at > datetime('now', '-10 minutes')""",
        (state,)
    )
    row = cursor.fetchone()
    if row:
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
        return dict(row)
    return None


def save_oauth_connection(
    conn,
    user_id: int,
    provider: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at: Optional[datetime],
    meta: Optional[dict],
):
    save_connection(
        conn=conn,
        user_id=user_id,
        provider=provider,
        auth_type="oauth2",
        secret=access_token,
        refresh_secret=refresh_token,
        expires_at=expires_at,
        scope=None,
        meta=meta,
    )


def delete_oauth_connection(conn, user_id: int, provider: str):
    delete_connection(conn, user_id, provider)


@router.get(
    "",
    response_model=list[IntegrationStatus],
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "integrations": {
                            "summary": "Connected integrations",
                            "value": [
                                {
                                    "name": "telegram",
                                    "display_name": "Telegram",
                                    "description": "Telegram messaging via MTProto user session",
                                    "is_configured": True,
                                    "is_connected": True,
                                    "connected_at": "2026-02-01T10:00:00",
                                    "meta": {"telegram_user_id": 12345, "username": "example"},
                                }
                            ],
                        }
                    }
                }
            }
        }
    },
)
async def list_integrations(current_user: User = Depends(get_current_user)):
    integrations = integration_registry.list_all()

    with get_db() as conn:
        connections = get_user_connections(conn, current_user.id)

    result = []
    for integration in integrations:
        connection = connections.get(integration.name)
        meta = None
        connected_at = None

        if connection:
            if connection.get("meta_json"):
                meta = json.loads(connection["meta_json"])
            connected_at = connection.get("created_at")

        result.append(IntegrationStatus(
            name=integration.name,
            display_name=integration.display_name,
            description=integration.description,
            is_configured=integration.is_configured(),
            is_connected=connection is not None,
            connected_at=connected_at,
            meta=meta,
        ))

    return result


@router.post(
    "/{name}/disconnect",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "disconnect": {
                            "summary": "Disconnected",
                            "value": {"message": "Disconnected from Telegram"},
                        }
                    }
                }
            }
        }
    },
)
async def disconnect_integration(
    name: str,
    current_user: User = Depends(get_current_user),
):
    integration = integration_registry.get(name)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    with get_db() as conn:
        delete_oauth_connection(conn, current_user.id, name)

    safe_audit_log(
        user_id=current_user.id,
        provider=name,
        action=f"{name}.disconnect",
        request_data=None,
        response_data={"disconnected": True},
        status="ok",
    )

    return {"message": f"Disconnected from {integration.display_name}"}


@oauth_router.get("/{provider}/start")
async def oauth_start(
    provider: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    integration = integration_registry.get(provider)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    if getattr(integration, "auth_type", "oauth2") != "oauth2":
        raise HTTPException(status_code=400, detail="Integration does not use OAuth")

    if not integration.is_configured():
        raise HTTPException(
            status_code=400,
            detail=f"{integration.display_name} is not configured"
        )

    state = secrets.token_urlsafe(32)
    redirect_uri = f"{get_public_base_url()}/oauth/{provider}/callback"

    with get_db() as conn:
        save_oauth_state(conn, state, current_user.id, provider)

    auth_url = integration.get_oauth_start_url(state, redirect_uri)
    return RedirectResponse(url=auth_url)


@oauth_router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    integration = integration_registry.get(provider)
    if not integration:
        return RedirectResponse(url="/?error=invalid_provider")

    if getattr(integration, "auth_type", "oauth2") != "oauth2":
        return RedirectResponse(url="/?error=unsupported_auth")

    if error:
        return RedirectResponse(
            url=f"/?error=oauth_error&provider={provider}&message={error}"
        )

    if not code or not state:
        return RedirectResponse(url="/?error=missing_params")

    with get_db() as conn:
        state_data = get_oauth_state(conn, state)

    if not state_data:
        return RedirectResponse(url="/?error=invalid_state")

    redirect_uri = f"{get_public_base_url()}/oauth/{provider}/callback"

    try:
        token_data = await integration.handle_oauth_callback(code, redirect_uri)

        expires_at = None
        if token_data.get("expires_in"):
            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=token_data["expires_in"]
            )

        with get_db() as conn:
            save_oauth_connection(
                conn,
                user_id=state_data["user_id"],
                provider=provider,
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token"),
                expires_at=expires_at,
                meta=token_data.get("meta"),
            )

        safe_audit_log(
            user_id=state_data["user_id"],
            provider=provider,
            action=f"{provider}.connect",
            request_data={"auth_type": "oauth2"},
            response_data=token_data.get("meta") or {"connected": True},
            status="ok",
        )

        return RedirectResponse(url=f"/?success=connected&provider={provider}")

    except Exception as e:
        return RedirectResponse(
            url=f"/?error=oauth_failed&provider={provider}&message={str(e)}"
        )


@router.post(
    "/telegram/start",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "start": {"summary": "Login started", "value": {"login_id": "login_id"}}
                    }
                }
            }
        }
    },
)
async def telegram_start(
    data: TelegramStartRequest,
    current_user: User = Depends(get_current_user),
):
    integration = integration_registry.get("telegram")
    if not integration or not integration.is_configured():
        raise HTTPException(status_code=400, detail="Telegram is not configured")

    try:
        login_id = await telegram_auth.start_login(current_user.id, data.phone)
        return {"login_id": login_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/telegram/verify",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "verified": {"summary": "Verified", "value": {"connected": True}},
                        "needs_password": {"summary": "2FA required", "value": {"requires_password": True}},
                    }
                }
            }
        }
    },
)
async def telegram_verify(
    data: TelegramVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await telegram_auth.verify_code(
            data.login_id, data.code, current_user.id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result.get("requires_password"):
        return {"requires_password": True}

    with get_db() as conn:
        save_connection(
            conn=conn,
            user_id=current_user.id,
            provider="telegram",
            auth_type="session",
            secret=result["session_string"],
            refresh_secret=None,
            expires_at=None,
            scope=None,
            meta=result.get("meta"),
        )

    safe_audit_log(
        user_id=current_user.id,
        provider="telegram",
        action="telegram.connect",
        request_data={"auth_type": "session"},
        response_data=result.get("meta") or {"connected": True},
        status="ok",
    )

    return {"connected": True}


@router.post(
    "/telegram/password",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "connected": {"summary": "Connected", "value": {"connected": True}}
                    }
                }
            }
        }
    },
)
async def telegram_password(
    data: TelegramPasswordRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        result = await telegram_auth.submit_password(
            data.login_id, data.password, current_user.id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    with get_db() as conn:
        save_connection(
            conn=conn,
            user_id=current_user.id,
            provider="telegram",
            auth_type="session",
            secret=result["session_string"],
            refresh_secret=None,
            expires_at=None,
            scope=None,
            meta=result.get("meta"),
        )

    safe_audit_log(
        user_id=current_user.id,
        provider="telegram",
        action="telegram.connect",
        request_data={"auth_type": "session"},
        response_data=result.get("meta") or {"connected": True},
        status="ok",
    )

    return {"connected": True}
