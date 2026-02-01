from datetime import datetime, timezone
from typing import Optional

from app.db import get_db
from app.auth.jwt import decode_token
from app.auth.hashing import hash_token
from app.models.user import UserStatus


def get_user_from_bearer(token: str) -> Optional[dict]:
    payload = decode_token(token)
    if payload and payload.get("type") == "access":
        user_id = int(payload["sub"])
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT id, email, role, is_active, status FROM users WHERE id = ?",
                (user_id,),
            )
            row = cursor.fetchone()
            if not row or not row["is_active"] or row["status"] != UserStatus.APPROVED.value:
                return None
            return {"id": row["id"], "email": row["email"], "role": row["role"]}
    return None


def get_user_from_pat(token: str) -> Optional[dict]:
    token_hash = hash_token(token)
    now = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cursor = conn.execute(
            """SELECT pat.user_id, u.email, u.role, u.is_active, u.status
               FROM personal_access_tokens pat
               JOIN users u ON pat.user_id = u.id
               WHERE pat.token_hash = ?
                 AND pat.expires_at > ?
                 AND u.is_active = 1
                 AND u.status = ?""",
            (token_hash, now, UserStatus.APPROVED.value),
        )
        row = cursor.fetchone()
        if not row:
            return None

        conn.execute(
            "UPDATE personal_access_tokens SET last_used_at = ? WHERE token_hash = ?",
            (now, token_hash),
        )
        conn.commit()
        return {"id": row["user_id"], "email": row["email"], "role": row["role"]}


def get_user_from_token(token: str) -> Optional[dict]:
    user = get_user_from_bearer(token)
    if user:
        return user
    return get_user_from_pat(token)
