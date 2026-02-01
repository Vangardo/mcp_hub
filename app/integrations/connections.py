import json
from datetime import datetime
from typing import Optional

from app.crypto import encrypt_token, decrypt_token


def get_user_connection(conn, user_id: int, provider: str) -> Optional[dict]:
    cursor = conn.execute(
        """SELECT * FROM connections
           WHERE user_id = ? AND provider = ? AND is_connected = 1""",
        (user_id, provider),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def get_user_connections(conn, user_id: int) -> dict[str, dict]:
    cursor = conn.execute(
        "SELECT * FROM connections WHERE user_id = ? AND is_connected = 1",
        (user_id,),
    )
    connections = {}
    for row in cursor.fetchall():
        row_dict = dict(row)
        connections[row_dict["provider"]] = row_dict
    return connections


def list_connected_providers(conn, user_id: int) -> list[str]:
    cursor = conn.execute(
        "SELECT provider FROM connections WHERE user_id = ? AND is_connected = 1",
        (user_id,),
    )
    return [row["provider"] for row in cursor.fetchall()]


def save_connection(
    conn,
    user_id: int,
    provider: str,
    auth_type: str,
    secret: str,
    refresh_secret: Optional[str],
    expires_at: Optional[datetime],
    scope: Optional[str],
    meta: Optional[dict],
):
    secret_enc = encrypt_token(secret)
    refresh_secret_enc = encrypt_token(refresh_secret) if refresh_secret else None
    expires_at_str = expires_at.isoformat() if expires_at else None
    meta_json = json.dumps(meta) if meta else None

    conn.execute(
        """INSERT INTO connections
           (user_id, provider, auth_type, secret_enc, refresh_secret_enc, expires_at, scope, meta_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, provider) DO UPDATE SET
               auth_type = excluded.auth_type,
               secret_enc = excluded.secret_enc,
               refresh_secret_enc = excluded.refresh_secret_enc,
               expires_at = excluded.expires_at,
               scope = excluded.scope,
               meta_json = excluded.meta_json,
               is_connected = 1,
               updated_at = datetime('now')""",
        (
            user_id,
            provider,
            auth_type,
            secret_enc,
            refresh_secret_enc,
            expires_at_str,
            scope,
            meta_json,
        ),
    )
    conn.commit()


def delete_connection(conn, user_id: int, provider: str):
    conn.execute(
        "DELETE FROM connections WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    conn.commit()


def decrypt_connection_secret(connection: dict) -> str:
    return decrypt_token(connection["secret_enc"])


def decrypt_connection_refresh_secret(connection: dict) -> Optional[str]:
    if not connection.get("refresh_secret_enc"):
        return None
    return decrypt_token(connection["refresh_secret_enc"])
