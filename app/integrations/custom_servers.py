import json
import re
from datetime import datetime, timezone
from typing import Optional

from app.crypto import encrypt_token, decrypt_token


RESERVED_SLUGS = {
    "hub", "teamwork", "slack", "miro", "figma",
    "telegram", "binance", "memory",
}


def slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "custom"


def get_user_custom_servers(conn, user_id: int) -> list[dict]:
    cursor = conn.execute(
        "SELECT * FROM custom_mcp_servers WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_custom_server(conn, user_id: int, slug: str) -> Optional[dict]:
    cursor = conn.execute(
        "SELECT * FROM custom_mcp_servers WHERE user_id = ? AND slug = ?",
        (user_id, slug),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_custom_server_by_id(conn, server_id: int, user_id: int) -> Optional[dict]:
    cursor = conn.execute(
        "SELECT * FROM custom_mcp_servers WHERE id = ? AND user_id = ?",
        (server_id, user_id),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def add_custom_server(
    conn,
    user_id: int,
    slug: str,
    display_name: str,
    server_url: str,
    auth_type: str = "none",
    auth_secret: Optional[str] = None,
    auth_header_name: Optional[str] = None,
) -> int:
    if slug in RESERVED_SLUGS:
        raise ValueError(f"Slug '{slug}' is reserved for system integrations")

    auth_secret_enc = encrypt_token(auth_secret) if auth_secret else None

    cursor = conn.execute(
        """INSERT INTO custom_mcp_servers
           (user_id, slug, display_name, server_url, auth_type,
            auth_secret_enc, auth_header_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, slug, display_name, server_url, auth_type,
         auth_secret_enc, auth_header_name),
    )
    conn.commit()
    return cursor.lastrowid


def update_custom_server(
    conn,
    server_id: int,
    user_id: int,
    display_name: Optional[str] = None,
    server_url: Optional[str] = None,
    auth_type: Optional[str] = None,
    auth_secret: Optional[str] = None,
    auth_header_name: Optional[str] = None,
    is_enabled: Optional[bool] = None,
):
    updates = []
    params = []

    if display_name is not None:
        updates.append("display_name = ?")
        params.append(display_name)
    if server_url is not None:
        updates.append("server_url = ?")
        params.append(server_url)
    if auth_type is not None:
        updates.append("auth_type = ?")
        params.append(auth_type)
    if auth_secret is not None:
        updates.append("auth_secret_enc = ?")
        params.append(encrypt_token(auth_secret))
    if auth_header_name is not None:
        updates.append("auth_header_name = ?")
        params.append(auth_header_name)
    if is_enabled is not None:
        updates.append("is_enabled = ?")
        params.append(1 if is_enabled else 0)

    if not updates:
        return

    updates.append("updated_at = datetime('now')")
    params.extend([server_id, user_id])

    conn.execute(
        f"UPDATE custom_mcp_servers SET {', '.join(updates)} WHERE id = ? AND user_id = ?",
        params,
    )
    conn.commit()


def delete_custom_server(conn, server_id: int, user_id: int):
    conn.execute(
        "DELETE FROM custom_mcp_servers WHERE id = ? AND user_id = ?",
        (server_id, user_id),
    )
    conn.commit()


def toggle_custom_server(conn, server_id: int, user_id: int, is_enabled: bool):
    conn.execute(
        """UPDATE custom_mcp_servers SET is_enabled = ?, updated_at = datetime('now')
           WHERE id = ? AND user_id = ?""",
        (1 if is_enabled else 0, server_id, user_id),
    )
    conn.commit()


def update_tools_cache(conn, server_id: int, tools_json: str):
    conn.execute(
        """UPDATE custom_mcp_servers
           SET tools_cache_json = ?, tools_cached_at = datetime('now'),
               updated_at = datetime('now')
           WHERE id = ?""",
        (tools_json, server_id),
    )
    conn.commit()


def update_health_status(conn, server_id: int, health_status: str):
    conn.execute(
        """UPDATE custom_mcp_servers
           SET health_status = ?, last_health_check = datetime('now'),
               updated_at = datetime('now')
           WHERE id = ?""",
        (health_status, server_id),
    )
    conn.commit()


def decrypt_server_auth_secret(server: dict) -> Optional[str]:
    if not server.get("auth_secret_enc"):
        return None
    return decrypt_token(server["auth_secret_enc"])
