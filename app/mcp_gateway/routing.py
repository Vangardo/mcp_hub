import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.db import get_db
from app.crypto import encrypt_token
from app.integrations.registry import integration_registry
from app.integrations.base import ToolResult
from app.integrations.connections import (
    get_user_connection,
    decrypt_connection_secret,
    decrypt_connection_refresh_secret,
)


def update_connection_tokens(
    conn,
    connection_id: int,
    access_token: str,
    refresh_token: Optional[str],
    expires_at: Optional[datetime],
):
    access_token_enc = encrypt_token(access_token)
    refresh_token_enc = encrypt_token(refresh_token) if refresh_token else None
    expires_at_str = expires_at.isoformat() if expires_at else None

    conn.execute(
        """UPDATE connections
           SET secret_enc = ?, refresh_secret_enc = ?, expires_at = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (access_token_enc, refresh_token_enc, expires_at_str, connection_id)
    )
    conn.commit()


def parse_tool_name(tool_name: str) -> tuple[str, str]:
    parts = tool_name.split(".", 1)
    if len(parts) < 2:
        raise ValueError(f"Invalid tool name format: {tool_name}")
    return parts[0], tool_name


async def get_access_token_for_provider(
    user_id: int, provider: str
) -> tuple[str, Optional[dict]]:
    # Memory is a built-in provider — no real token, pass user_id
    if provider == "memory":
        return str(user_id), None

    with get_db() as conn:
        connection = get_user_connection(conn, user_id, provider)

    if not connection:
        raise ValueError(f"No connection found for {provider}")

    access_token = decrypt_connection_secret(connection)
    meta = json.loads(connection["meta_json"]) if connection.get("meta_json") else None

    if connection.get("auth_type") == "oauth2" and connection.get("expires_at"):
        expires_at = datetime.fromisoformat(connection["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
            if connection.get("refresh_secret_enc"):
                integration = integration_registry.get(provider)
                if integration:
                    refresh_token = decrypt_connection_refresh_secret(connection)
                    try:
                        new_tokens = await integration.refresh_access_token(refresh_token)
                        access_token = new_tokens["access_token"]

                        new_expires_at = None
                        if new_tokens.get("expires_in"):
                            new_expires_at = datetime.now(timezone.utc) + timedelta(
                                seconds=new_tokens["expires_in"]
                            )

                        with get_db() as conn:
                            update_connection_tokens(
                                conn,
                                connection["id"],
                                new_tokens["access_token"],
                                new_tokens.get("refresh_token"),
                                new_expires_at,
                            )
                    except Exception as e:
                        raise ValueError(f"Token refresh failed: {e}")
            else:
                raise ValueError("Access token expired and no refresh token available")

    return access_token, meta


async def execute_tool(
    user_id: int, tool_name: str, arguments: dict
) -> ToolResult:
    try:
        provider, full_tool_name = parse_tool_name(tool_name)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))

    integration = integration_registry.get(provider)
    if not integration:
        return ToolResult(success=False, error=f"Unknown integration: {provider}")

    try:
        access_token, meta = await get_access_token_for_provider(user_id, provider)
    except ValueError as e:
        return ToolResult(success=False, error=str(e))

    return await integration.execute_tool(full_tool_name, arguments, access_token, meta)
