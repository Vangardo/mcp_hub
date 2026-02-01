from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import get_current_user
from app.auth.jwt import create_access_token
from app.db import get_db
from app.models.user import User
from app.config.store import get_public_base_url
from app.integrations.connections import list_connected_providers
from app.integrations.registry import integration_registry


router = APIRouter(prefix="/config", tags=["config"])


@router.get(
    "/mcp",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "config": {
                            "summary": "MCP config",
                            "value": {
                                "mcpServers": {
                                    "mcp-hub": {
                                        "url": "http://localhost:8000/mcp",
                                        "headers": {"Authorization": "Bearer <TOKEN>"},
                                    },
                                    "mcp-hub-telegram": {
                                        "url": "http://localhost:8000/mcp",
                                        "headers": {
                                            "Authorization": "Bearer <TOKEN>",
                                            "X-MCP-Provider": "telegram",
                                        },
                                    },
                                }
                            },
                        }
                    }
                }
            }
        }
    },
)
async def get_mcp_config(
    current_user: User = Depends(get_current_user),
    provider: str | None = Query(None),
):
    access_token = create_access_token(
        user_id=current_user.id,
        email=current_user.email,
        role=current_user.role.value,
    )

    mcp_url = f"{get_public_base_url()}/mcp"

    with get_db() as conn:
        connected = list_connected_providers(conn, current_user.id)

    if provider:
        if provider not in connected:
            raise HTTPException(status_code=400, detail="Provider not connected")
        return {
            "mcpServers": {
                f"mcp-hub-{provider}": {
                    "url": mcp_url,
                    "headers": {
                        "Authorization": f"Bearer {access_token}",
                        "X-MCP-Provider": provider,
                    },
                }
            }
        }

    servers: dict[str, dict] = {
        "mcp-hub": {
            "url": mcp_url,
            "headers": {
                "Authorization": f"Bearer {access_token}"
            }
        }
    }

    configured = {i.name for i in integration_registry.list_configured()}
    for provider_name in connected:
        if provider_name not in configured:
            continue
        servers[f"mcp-hub-{provider_name}"] = {
            "url": mcp_url,
            "headers": {
                "Authorization": f"Bearer {access_token}",
                "X-MCP-Provider": provider_name,
            },
        }

    return {"mcpServers": servers}


@router.get(
    "/mcp/raw",
    responses={
        200: {
            "content": {
                "application/json": {
                    "examples": {
                        "raw": {
                            "summary": "Raw MCP config",
                            "value": {
                                "url": "http://localhost:8000/mcp",
                                "token": "eyJhbGciOi...",
                                "headers": {"Authorization": "Bearer eyJhbGciOi..."},
                                "user": {"id": 1, "email": "user@example.com"},
                            },
                        }
                    }
                }
            }
        }
    },
)
async def get_mcp_config_raw(
    current_user: User = Depends(get_current_user),
    provider: str | None = Query(None),
):
    access_token = create_access_token(
        user_id=current_user.id,
        email=current_user.email,
        role=current_user.role.value,
    )

    mcp_url = f"{get_public_base_url()}/mcp"
    headers = {"Authorization": f"Bearer {access_token}"}
    if provider:
        headers["X-MCP-Provider"] = provider

    return {
        "url": mcp_url,
        "token": access_token,
        "headers": headers,
        "user": {
            "id": current_user.id,
            "email": current_user.email,
        }
    }
