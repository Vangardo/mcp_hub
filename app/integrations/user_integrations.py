from typing import Optional


def get_user_integrations(conn, user_id: int) -> list[dict]:
    cursor = conn.execute(
        "SELECT * FROM user_integrations WHERE user_id = ? ORDER BY position, created_at",
        (user_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_user_enabled_providers(conn, user_id: int) -> set[str]:
    cursor = conn.execute(
        "SELECT provider FROM user_integrations WHERE user_id = ? AND is_enabled = 1",
        (user_id,),
    )
    return {row["provider"] for row in cursor.fetchall()}


def is_integration_added(conn, user_id: int, provider: str) -> bool:
    cursor = conn.execute(
        "SELECT 1 FROM user_integrations WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    return cursor.fetchone() is not None


def add_user_integration(conn, user_id: int, provider: str, position: int = 0):
    conn.execute(
        """INSERT OR IGNORE INTO user_integrations (user_id, provider, is_enabled, position)
           VALUES (?, ?, 1, ?)""",
        (user_id, provider, position),
    )
    conn.commit()


def remove_user_integration(conn, user_id: int, provider: str):
    conn.execute(
        "DELETE FROM user_integrations WHERE user_id = ? AND provider = ?",
        (user_id, provider),
    )
    conn.commit()


def toggle_user_integration(conn, user_id: int, provider: str, is_enabled: bool):
    conn.execute(
        """UPDATE user_integrations SET is_enabled = ?, updated_at = datetime('now')
           WHERE user_id = ? AND provider = ?""",
        (1 if is_enabled else 0, user_id, provider),
    )
    conn.commit()


def ensure_memory_integration(conn, user_id: int):
    conn.execute(
        """INSERT OR IGNORE INTO user_integrations (user_id, provider, is_enabled, position)
           VALUES (?, 'memory', 1, 0)""",
        (user_id,),
    )
    conn.commit()
