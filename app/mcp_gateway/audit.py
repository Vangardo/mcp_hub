import json
from typing import Optional, Any

from app.db import get_db


def log_tool_call(
    user_id: Optional[int],
    provider: Optional[str],
    action: str,
    request_data: Optional[dict],
    response_data: Optional[Any],
    status: str,
    tool_name: Optional[str] = None,
    error_text: Optional[str] = None,
):
    request_json = json.dumps(request_data) if request_data else None
    response_json = json.dumps(response_data) if response_data else None

    with get_db() as conn:
        conn.execute(
            """INSERT INTO audit_logs
               (user_id, provider, action, tool_name, request_json, response_json, status, error_text)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, provider, action, tool_name, request_json, response_json, status, error_text)
        )
        conn.commit()
