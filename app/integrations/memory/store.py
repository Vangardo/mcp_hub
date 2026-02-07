"""Database CRUD and FTS5 search for memory items."""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional


def generate_id() -> str:
    return str(uuid.uuid4())


def _ensure_unicode_json(value: str) -> str:
    """Re-encode JSON string to ensure no \\uXXXX escapes for readable Unicode."""
    try:
        parsed = json.loads(value)
        return json.dumps(parsed, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError, ValueError):
        return value


def _row_to_dict(row) -> dict:
    d = dict(row)
    d["pinned"] = bool(d.get("pinned", 0))

    raw_val = d.get("value_json", "{}")
    try:
        parsed = json.loads(raw_val)
        d["value"] = parsed
        if isinstance(parsed, (dict, list)):
            d["value_display"] = json.dumps(parsed, ensure_ascii=False, indent=2)
        else:
            d["value_display"] = str(parsed)
    except (json.JSONDecodeError, TypeError):
        d["value"] = raw_val
        d["value_display"] = raw_val

    try:
        d["tags"] = json.loads(d.get("tags_json", "[]"))
    except (json.JSONDecodeError, TypeError):
        d["tags"] = []
    try:
        d["source"] = json.loads(d.get("source_json") or "null")
    except (json.JSONDecodeError, TypeError):
        d["source"] = None
    return d


def upsert_item(conn, user_id: int, item: dict) -> dict:
    item_id = item.get("id") or generate_id()
    item_type = item.get("type", "note")
    scope = item.get("scope", "global")
    title = item.get("title", "")
    value_json = item.get("value_json", "{}")
    if isinstance(value_json, (dict, list)):
        value_json = json.dumps(value_json, ensure_ascii=False)
    elif isinstance(value_json, str):
        value_json = _ensure_unicode_json(value_json)
    else:
        value_json = json.dumps(value_json, ensure_ascii=False)
    tags_json = item.get("tags_json", "[]")
    if isinstance(tags_json, (list, tuple)):
        tags_json = json.dumps(tags_json, ensure_ascii=False)
    elif isinstance(tags_json, str):
        tags_json = _ensure_unicode_json(tags_json)
    pinned = 1 if item.get("pinned") else 0
    ttl_days = item.get("ttl_days")
    sensitivity = item.get("sensitivity", "low")
    confidence = item.get("confidence", 1.0)
    source_json = item.get("source_json")
    if isinstance(source_json, dict):
        source_json = json.dumps(source_json, ensure_ascii=False)

    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO memory_items
           (id, user_id, type, scope, title, value_json, tags_json, pinned,
            ttl_days, sensitivity, confidence, source_json, created_at, updated_at, version)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
           ON CONFLICT(user_id, type, scope, title) DO UPDATE SET
             value_json = excluded.value_json,
             tags_json = excluded.tags_json,
             pinned = excluded.pinned,
             ttl_days = excluded.ttl_days,
             sensitivity = excluded.sensitivity,
             confidence = excluded.confidence,
             source_json = excluded.source_json,
             updated_at = excluded.updated_at,
             version = memory_items.version + 1
        """,
        (
            item_id, user_id, item_type, scope, title, value_json, tags_json,
            pinned, ttl_days, sensitivity, confidence, source_json, now, now,
        ),
    )
    conn.commit()

    # Return the actual saved item
    row = conn.execute(
        "SELECT * FROM memory_items WHERE user_id = ? AND type = ? AND scope = ? AND title = ?",
        (user_id, item_type, scope, title),
    ).fetchone()
    return _row_to_dict(row) if row else {"id": item_id}


def get_item(conn, user_id: int, item_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT * FROM memory_items WHERE id = ? AND user_id = ?",
        (item_id, user_id),
    ).fetchone()
    return _row_to_dict(row) if row else None


def delete_item(conn, user_id: int, item_id: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM memory_items WHERE id = ? AND user_id = ?",
        (item_id, user_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def delete_by_title(conn, user_id: int, title: str, item_type: Optional[str] = None, scope: Optional[str] = None) -> bool:
    sql = "DELETE FROM memory_items WHERE user_id = ? AND title = ?"
    params: list = [user_id, title]
    if item_type:
        sql += " AND type = ?"
        params.append(item_type)
    if scope:
        sql += " AND scope = ?"
        params.append(scope)
    cursor = conn.execute(sql, params)
    conn.commit()
    return cursor.rowcount > 0


def pin_item(conn, user_id: int, item_id: str, pinned: bool) -> bool:
    cursor = conn.execute(
        "UPDATE memory_items SET pinned = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (1 if pinned else 0, item_id, user_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def set_ttl(conn, user_id: int, item_id: str, ttl_days: Optional[int]) -> bool:
    cursor = conn.execute(
        "UPDATE memory_items SET ttl_days = ?, updated_at = datetime('now') WHERE id = ? AND user_id = ?",
        (ttl_days, item_id, user_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def search_items(
    conn,
    user_id: int,
    query: str,
    filters: Optional[dict] = None,
    top_k: int = 20,
) -> list[dict]:
    filters = filters or {}

    # FTS5 search
    sql = """
        SELECT m.* FROM memory_items m
        JOIN memory_items_fts f ON m.rowid = f.rowid
        WHERE f.memory_items_fts MATCH ? AND m.user_id = ?
    """
    params: list = [query, user_id]

    # Apply filters
    if filters.get("type"):
        types = filters["type"] if isinstance(filters["type"], list) else [filters["type"]]
        placeholders = ",".join("?" * len(types))
        sql += f" AND m.type IN ({placeholders})"
        params.extend(types)
    if filters.get("scope"):
        sql += " AND m.scope = ?"
        params.append(filters["scope"])
    if filters.get("pinned") is not None:
        sql += " AND m.pinned = ?"
        params.append(1 if filters["pinned"] else 0)
    if filters.get("sensitivity"):
        sql += " AND m.sensitivity = ?"
        params.append(filters["sensitivity"])

    sql += " ORDER BY rank LIMIT ?"
    params.append(top_k)

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def list_items(
    conn,
    user_id: int,
    filters: Optional[dict] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    filters = filters or {}

    sql = "SELECT * FROM memory_items WHERE user_id = ?"
    params: list = [user_id]

    if filters.get("type"):
        types = filters["type"] if isinstance(filters["type"], list) else [filters["type"]]
        placeholders = ",".join("?" * len(types))
        sql += f" AND type IN ({placeholders})"
        params.extend(types)
    if filters.get("scope"):
        sql += " AND scope = ?"
        params.append(filters["scope"])
    if filters.get("pinned") is not None:
        sql += " AND pinned = ?"
        params.append(1 if filters["pinned"] else 0)

    sql += " ORDER BY pinned DESC, updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(r) for r in rows]


def get_context_pack(
    conn,
    user_id: int,
    scope: str = "auto",
    max_per_section: int = 10,
) -> dict:
    # Clean up expired items first
    cleanup_expired(conn, user_id)

    base_filter = "user_id = ?"
    params_base = [user_id]

    scope_filter = ""
    if scope not in ("auto", "global", "all"):
        scope_filter = " AND (scope = ? OR scope = 'global')"
        params_base.append(scope)

    def query(extra_where: str, extra_params: list, limit: int = max_per_section):
        sql = f"SELECT * FROM memory_items WHERE {base_filter}{scope_filter}{extra_where} ORDER BY updated_at DESC LIMIT ?"
        return [
            _row_to_dict(r)
            for r in conn.execute(sql, params_base + extra_params + [limit]).fetchall()
        ]

    return {
        "pinned": query(" AND pinned = 1", []),
        "preferences": query(" AND type = 'preference'", []),
        "constraints": query(" AND type = 'constraint'", []),
        "active_projects": query(" AND type IN ('project', 'goal')", []),
        "watchlist": query(" AND type = 'asset'", []),
        "contacts": query(" AND type = 'contact'", []),
        "recent": query(" AND ttl_days IS NOT NULL", [], limit=max_per_section),
    }


def cleanup_expired(conn, user_id: int) -> int:
    cursor = conn.execute(
        """DELETE FROM memory_items
           WHERE user_id = ? AND ttl_days IS NOT NULL
             AND datetime(created_at, '+' || ttl_days || ' days') < datetime('now')""",
        (user_id,),
    )
    if cursor.rowcount > 0:
        conn.commit()
    return cursor.rowcount


def count_items(conn, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM memory_items WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    return row["cnt"] if row else 0
