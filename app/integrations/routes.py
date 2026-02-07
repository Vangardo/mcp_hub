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
from app.integrations.user_integrations import (
    add_user_integration,
    remove_user_integration,
    toggle_user_integration,
    is_integration_added,
)
from app.integrations.custom_servers import (
    get_user_custom_servers,
    get_custom_server_by_id,
    add_custom_server,
    delete_custom_server,
    toggle_custom_server,
    update_tools_cache,
    update_health_status,
    decrypt_server_auth_secret,
    slugify,
    RESERVED_SLUGS,
)
from app.integrations.mcp_proxy import MCPProxyClient


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


class FigmaTokenRequest(BaseModel):
    token: str
    model_config = {
        "json_schema_extra": {"examples": [{"token": "figd_..."}]}
    }


class BinanceTokenRequest(BaseModel):
    api_key: str
    api_secret: str
    model_config = {
        "json_schema_extra": {
            "examples": [{"api_key": "your_api_key", "api_secret": "your_api_secret"}]
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
        return RedirectResponse(url=f"/?error=not_found&message=Integration+not+found")

    if getattr(integration, "auth_type", "oauth2") != "oauth2":
        return RedirectResponse(url=f"/?error=unsupported&message=Integration+does+not+use+OAuth")

    if not integration.is_configured():
        return RedirectResponse(
            url=f"/?error=not_configured&message={integration.display_name}+is+not+configured.+Ask+admin+to+set+up+credentials."
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
            # Auto-add to user's dashboard when connecting
            add_user_integration(conn, state_data["user_id"], provider)

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
    "/figma/token",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "connected": {
                            "summary": "Connected via PAT",
                            "value": {
                                "success": True,
                                "meta": {"user_id": "123", "handle": "designer", "email": "user@example.com"},
                            },
                        }
                    }
                }
            }
        }
    },
)
async def figma_token_connect(
    data: FigmaTokenRequest,
    current_user: User = Depends(get_current_user),
):
    import httpx

    token = data.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.figma.com/v1/me",
                headers={"X-Figma-Token": token},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Failed to connect to Figma API: {e}")

    if resp.status_code == 403:
        raise HTTPException(
            status_code=400,
            detail="Access denied. Token may have insufficient scopes or be expired.",
        )
    if resp.status_code != 200:
        body = resp.text[:200]
        raise HTTPException(
            status_code=400,
            detail=f"Figma API error (HTTP {resp.status_code}): {body}",
        )

    try:
        me = resp.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid response from Figma API")

    meta = {
        "user_id": me.get("id"),
        "handle": me.get("handle"),
        "email": me.get("email"),
        "img_url": me.get("img_url"),
    }

    with get_db() as conn:
        save_connection(
            conn=conn,
            user_id=current_user.id,
            provider="figma",
            auth_type="pat",
            secret=token,
            refresh_secret=None,
            expires_at=None,
            scope=None,
            meta=meta,
        )
        add_user_integration(conn, current_user.id, "figma")

    safe_audit_log(
        user_id=current_user.id,
        provider="figma",
        action="figma.connect",
        request_data={"auth_type": "pat"},
        response_data=meta,
        status="ok",
    )

    return {"success": True, "meta": meta}


@router.post(
    "/binance/token",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "connected": {
                            "summary": "Connected via API Key",
                            "value": {
                                "success": True,
                                "meta": {"permissions": ["SPOT"]},
                            },
                        }
                    }
                }
            }
        }
    },
)
async def binance_token_connect(
    data: BinanceTokenRequest,
    current_user: User = Depends(get_current_user),
):
    import httpx
    import hmac
    import hashlib
    import time
    from urllib.parse import urlencode

    import logging
    logger = logging.getLogger(__name__)

    api_key = data.api_key.strip()
    api_secret = data.api_secret.strip()
    if not api_key or not api_secret:
        raise HTTPException(status_code=400, detail="API Key and Secret are required")

    # Validate credentials by calling /api/v3/account
    timestamp = int(time.time() * 1000)
    params = {"timestamp": timestamp}
    query_string = urlencode(params)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    params["signature"] = signature

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.binance.com/api/v3/account",
                headers={"X-MBX-APIKEY": api_key},
                params=params,
            )
    except httpx.ConnectError as e:
        logger.error("Binance connect error: %s", e)
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reach Binance API. Check your network or try api1.binance.com. Error: {e}",
        )
    except httpx.TimeoutException as e:
        logger.error("Binance timeout: %s", e)
        raise HTTPException(status_code=400, detail=f"Binance API request timed out: {e}")
    except httpx.HTTPError as e:
        logger.error("Binance HTTP error: %s", e)
        raise HTTPException(status_code=400, detail=f"Failed to connect to Binance API: {e}")

    body_text = resp.text[:500]
    logger.info("Binance /account response: status=%d body=%s", resp.status_code, body_text)

    # Parse Binance error response for detailed message
    binance_msg = ""
    try:
        err_json = resp.json()
        binance_msg = err_json.get("msg", "")
        binance_code = err_json.get("code", "")
        if binance_code:
            binance_msg = f"[{binance_code}] {binance_msg}"
    except Exception:
        binance_msg = body_text

    if resp.status_code == 401:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid API Key. Binance: {binance_msg}",
        )
    if resp.status_code == 403:
        raise HTTPException(
            status_code=400,
            detail=f"Access denied. Check API Key permissions or IP restrictions. Binance: {binance_msg}",
        )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Binance API error (HTTP {resp.status_code}): {binance_msg}",
        )

    try:
        account = resp.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid response from Binance API")

    # Extract permissions and balance summary
    permissions = account.get("permissions", [])
    balances = account.get("balances", [])
    non_zero = [
        b for b in balances
        if float(b.get("free", 0)) > 0 or float(b.get("locked", 0)) > 0
    ]
    asset_summary = ", ".join(b["asset"] for b in non_zero[:5])
    if len(non_zero) > 5:
        asset_summary += f" +{len(non_zero) - 5} more"

    meta = {
        "permissions": permissions,
        "asset_count": len(non_zero),
        "top_assets": asset_summary,
    }

    # Store as JSON: {"api_key": "...", "api_secret": "..."}
    token_json = json.dumps({"api_key": api_key, "api_secret": api_secret})

    with get_db() as conn:
        save_connection(
            conn=conn,
            user_id=current_user.id,
            provider="binance",
            auth_type="pat",
            secret=token_json,
            refresh_secret=None,
            expires_at=None,
            scope=None,
            meta=meta,
        )
        add_user_integration(conn, current_user.id, "binance")

    safe_audit_log(
        user_id=current_user.id,
        provider="binance",
        action="binance.connect",
        request_data={"auth_type": "api_key"},
        response_data=meta,
        status="ok",
    )

    return {"success": True, "meta": meta}


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
        add_user_integration(conn, current_user.id, "telegram")

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
        add_user_integration(conn, current_user.id, "telegram")

    safe_audit_log(
        user_id=current_user.id,
        provider="telegram",
        action="telegram.connect",
        request_data={"auth_type": "session"},
        response_data=result.get("meta") or {"connected": True},
        status="ok",
    )

    return {"connected": True}


# ── Dashboard management ─────────────────────────────────────────────


class AddIntegrationRequest(BaseModel):
    provider: str


class ToggleIntegrationRequest(BaseModel):
    is_enabled: bool


@router.post("/dashboard/add")
async def add_integration_to_dashboard(
    data: AddIntegrationRequest,
    current_user: User = Depends(get_current_user),
):
    integration = integration_registry.get(data.provider)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    with get_db() as conn:
        add_user_integration(conn, current_user.id, data.provider)

    return {"message": f"Added {integration.display_name}"}


@router.post("/dashboard/{provider}/remove")
async def remove_integration_from_dashboard(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        remove_user_integration(conn, current_user.id, provider)
        delete_connection(conn, current_user.id, provider)

    return {"message": "Removed"}


@router.post("/dashboard/{provider}/toggle")
async def toggle_integration_visibility(
    provider: str,
    data: ToggleIntegrationRequest,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        toggle_user_integration(conn, current_user.id, provider, data.is_enabled)

    return {"message": "Toggled", "is_enabled": data.is_enabled}


# ── Custom MCP servers ───────────────────────────────────────────────


class AddCustomServerRequest(BaseModel):
    display_name: str
    server_url: str
    auth_type: str = "none"
    auth_secret: Optional[str] = None
    auth_header_name: Optional[str] = None


@router.post("/custom-servers")
async def add_custom_server_endpoint(
    data: AddCustomServerRequest,
    current_user: User = Depends(get_current_user),
):
    slug = slugify(data.display_name)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid display name")
    if slug in RESERVED_SLUGS:
        raise HTTPException(status_code=400, detail=f"Name '{slug}' is reserved")

    proxy = MCPProxyClient(
        server_url=data.server_url,
        auth_type=data.auth_type,
        auth_secret=data.auth_secret,
        auth_header_name=data.auth_header_name,
        timeout=15.0,
    )

    try:
        await proxy.initialize()
        tools = await proxy.list_tools()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect to MCP server: {e}",
        )

    with get_db() as conn:
        server_id = add_custom_server(
            conn,
            user_id=current_user.id,
            slug=slug,
            display_name=data.display_name,
            server_url=data.server_url,
            auth_type=data.auth_type,
            auth_secret=data.auth_secret,
            auth_header_name=data.auth_header_name,
        )
        update_tools_cache(conn, server_id, json.dumps(tools, default=str))
        update_health_status(conn, server_id, "healthy")

    return {"id": server_id, "slug": slug, "tools_count": len(tools), "tools": tools}


@router.get("/custom-servers")
async def list_custom_servers_endpoint(
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        servers = get_user_custom_servers(conn, current_user.id)
    return {"servers": servers}


@router.delete("/custom-servers/{server_id}")
async def delete_custom_server_endpoint(
    server_id: int,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        server = get_custom_server_by_id(conn, server_id, current_user.id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        delete_custom_server(conn, server_id, current_user.id)

    return {"message": "Deleted"}


@router.post("/custom-servers/{server_id}/toggle")
async def toggle_custom_server_endpoint(
    server_id: int,
    data: ToggleIntegrationRequest,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        server = get_custom_server_by_id(conn, server_id, current_user.id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        toggle_custom_server(conn, server_id, current_user.id, data.is_enabled)

    return {"message": "Toggled", "is_enabled": data.is_enabled}


@router.post("/custom-servers/{server_id}/refresh")
async def refresh_custom_server_endpoint(
    server_id: int,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        server = get_custom_server_by_id(conn, server_id, current_user.id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    auth_secret = decrypt_server_auth_secret(server)
    proxy = MCPProxyClient(
        server_url=server["server_url"],
        auth_type=server["auth_type"],
        auth_secret=auth_secret,
        auth_header_name=server.get("auth_header_name"),
        timeout=15.0,
    )

    try:
        await proxy.initialize()
        tools = await proxy.list_tools()
        with get_db() as conn:
            update_tools_cache(conn, server_id, json.dumps(tools, default=str))
            update_health_status(conn, server_id, "healthy")
        return {"status": "healthy", "tools_count": len(tools), "tools": tools}
    except Exception as e:
        with get_db() as conn:
            update_health_status(conn, server_id, "unhealthy")
        raise HTTPException(status_code=400, detail=f"Health check failed: {e}")
