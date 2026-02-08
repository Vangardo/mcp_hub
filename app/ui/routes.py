from typing import Optional
from urllib.parse import quote
import json
import os

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.db import get_db
from app.auth.deps import get_current_user_optional, get_current_user, require_admin
from app.auth.hashing import verify_password, hash_password
from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.routes import save_refresh_token
from app.models.user import User, UserRole, UserStatus
from app.integrations.registry import integration_registry
from app.config.store import (
    PUBLIC_BASE_URL_KEY,
    PUBLIC_HOST_KEY,
    TEAMWORK_CLIENT_ID_KEY,
    TEAMWORK_CLIENT_SECRET_KEY,
    SLACK_CLIENT_ID_KEY,
    SLACK_CLIENT_SECRET_KEY,
    MIRO_CLIENT_ID_KEY,
    MIRO_CLIENT_SECRET_KEY,
    FIGMA_CLIENT_ID_KEY,
    FIGMA_CLIENT_SECRET_KEY,
    TELEGRAM_API_ID_KEY,
    TELEGRAM_API_HASH_KEY,
    get_setting_value,
)
from app.integrations.connections import get_user_connections, delete_connection
from app.integrations.user_integrations import (
    get_user_integrations,
    add_user_integration,
    remove_user_integration,
    toggle_user_integration,
    ensure_memory_integration,
)
from app.integrations.custom_servers import get_user_custom_servers


router = APIRouter(tags=["ui"])

# Надежное определение пути к шаблонам
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def get_user_by_email(conn, email: str) -> Optional[dict]:
    cursor = conn.execute(
        "SELECT * FROM users WHERE email = ? AND is_active = 1",
        (email,)
    )
    row = cursor.fetchone()
    return dict(row) if row else None


PROVIDER_COLORS = {
    "teamwork": "#8b5cf6",
    "slack": "#10b981",
    "miro": "#f59e0b",
    "figma": "#ec4899",
    "telegram": "#0ea5e9",
    "binance": "#d97706",
    "memory": "#6366f1",
    "hub": "#6366f1",
}


def _build_dashboard_stats(
    conn, period: str, user_id: Optional[int] = None, is_admin: bool = False
) -> dict:
    period_map = {
        "24h": "datetime(a.created_at) >= datetime('now', '-1 day')",
        "7d": "datetime(a.created_at) >= datetime('now', '-7 days')",
        "30d": "datetime(a.created_at) >= datetime('now', '-30 days')",
        "all": "1=1",
    }
    period_sql = period_map.get(period, period_map["7d"])

    user_sql = "a.user_id = ?" if user_id else "1=1"
    user_params = [user_id] if user_id else []
    where = f"{period_sql} AND {user_sql}"

    # KPI
    total_calls = conn.execute(
        f"SELECT COUNT(*) as c FROM audit_logs a WHERE {user_sql}", user_params
    ).fetchone()["c"]

    period_calls = conn.execute(
        f"SELECT COUNT(*) as c FROM audit_logs a WHERE {where}", user_params
    ).fetchone()["c"]

    errors_period = conn.execute(
        f"SELECT COUNT(*) as c FROM audit_logs a WHERE {where} AND a.status = 'error'",
        user_params,
    ).fetchone()["c"]

    success_rate = round(
        ((period_calls - errors_period) / period_calls * 100) if period_calls > 0 else 100, 1
    )

    if user_id:
        active_intgs = conn.execute(
            "SELECT COUNT(*) as c FROM connections WHERE user_id = ? AND is_connected = 1",
            (user_id,),
        ).fetchone()["c"]
        memory_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory_items WHERE user_id = ?", (user_id,)
        ).fetchone()["c"]
        recent_memory = conn.execute(
            "SELECT COUNT(*) as c FROM memory_items WHERE user_id = ? AND datetime(created_at) >= datetime('now', '-7 days')",
            (user_id,),
        ).fetchone()["c"]
    else:
        active_intgs = conn.execute(
            "SELECT COUNT(*) as c FROM connections WHERE is_connected = 1"
        ).fetchone()["c"]
        memory_count = conn.execute(
            "SELECT COUNT(*) as c FROM memory_items"
        ).fetchone()["c"]
        recent_memory = conn.execute(
            "SELECT COUNT(*) as c FROM memory_items WHERE datetime(created_at) >= datetime('now', '-7 days')"
        ).fetchone()["c"]

    kpi = {
        "total_calls": total_calls,
        "calls_period": period_calls,
        "success_rate": success_rate,
        "errors": errors_period,
        "active_integrations": active_intgs,
        "memory_items": memory_count,
    }

    # Timeline
    if period == "24h":
        bucket_expr = "strftime('%Y-%m-%d %H:00', a.created_at)"
    elif period in ("7d", "30d"):
        bucket_expr = "date(a.created_at)"
    else:
        bucket_expr = "strftime('%Y-%m', a.created_at)"

    timeline_rows = conn.execute(
        f"""SELECT {bucket_expr} as bucket,
                   SUM(CASE WHEN a.status = 'ok' THEN 1 ELSE 0 END) as ok_count,
                   SUM(CASE WHEN a.status = 'error' THEN 1 ELSE 0 END) as err_count
            FROM audit_logs a WHERE {where}
            GROUP BY bucket ORDER BY bucket""",
        user_params,
    ).fetchall()

    timeline = {
        "labels": [r["bucket"] for r in timeline_rows],
        "ok": [r["ok_count"] for r in timeline_rows],
        "error": [r["err_count"] for r in timeline_rows],
    }

    # Provider usage
    provider_rows = conn.execute(
        f"""SELECT a.provider, COUNT(*) as cnt
            FROM audit_logs a WHERE {where} AND a.provider IS NOT NULL
            GROUP BY a.provider ORDER BY cnt DESC""",
        user_params,
    ).fetchall()

    providers = {
        "labels": [r["provider"] for r in provider_rows],
        "values": [r["cnt"] for r in provider_rows],
        "colors": [PROVIDER_COLORS.get(r["provider"], "#64748b") for r in provider_rows],
    }

    # Success vs errors by provider
    err_prov_rows = conn.execute(
        f"""SELECT a.provider,
                   SUM(CASE WHEN a.status = 'ok' THEN 1 ELSE 0 END) as ok_count,
                   SUM(CASE WHEN a.status = 'error' THEN 1 ELSE 0 END) as err_count
            FROM audit_logs a WHERE {where} AND a.provider IS NOT NULL
            GROUP BY a.provider ORDER BY ok_count + err_count DESC""",
        user_params,
    ).fetchall()

    errors_by_provider = {
        "labels": [r["provider"] for r in err_prov_rows],
        "ok": [r["ok_count"] for r in err_prov_rows],
        "error": [r["err_count"] for r in err_prov_rows],
    }

    # Top tools
    top_tools_rows = conn.execute(
        f"""SELECT COALESCE(a.tool_name, a.action) as tool, COUNT(*) as cnt
            FROM audit_logs a WHERE {where}
            GROUP BY tool ORDER BY cnt DESC LIMIT 10""",
        user_params,
    ).fetchall()

    top_tools = {
        "labels": [r["tool"] for r in top_tools_rows],
        "values": [r["cnt"] for r in top_tools_rows],
    }

    result = {
        "kpi": kpi,
        "timeline": timeline,
        "providers": providers,
        "errors_by_provider": errors_by_provider,
        "top_tools": top_tools,
        "memory": {"total": memory_count, "recent_count": recent_memory},
    }

    if is_admin:
        active_users_rows = conn.execute(
            f"""SELECT {bucket_expr} as bucket, COUNT(DISTINCT a.user_id) as user_count
                FROM audit_logs a WHERE {where}
                GROUP BY bucket ORDER BY bucket""",
            user_params,
        ).fetchall()
        result["active_users"] = {
            "labels": [r["bucket"] for r in active_users_rows],
            "values": [r["user_count"] for r in active_users_rows],
        }

        top_users_rows = conn.execute(
            f"""SELECT u.email, COUNT(*) as cnt
                FROM audit_logs a LEFT JOIN users u ON a.user_id = u.id
                WHERE {where} AND a.user_id IS NOT NULL
                GROUP BY a.user_id ORDER BY cnt DESC LIMIT 10""",
            user_params,
        ).fetchall()
        result["top_users"] = {
            "labels": [r["email"] or "Unknown" for r in top_users_rows],
            "values": [r["cnt"] for r in top_users_rows],
        }

    return result


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": {"email": user.email, "role": user.role.value},
            "active_page": "dashboard",
        },
    )


@router.get("/integrations", response_class=HTMLResponse)
async def integrations_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    with get_db() as conn:
        ensure_memory_integration(conn, user.id)
        user_intgs = get_user_integrations(conn, user.id)
        connections = get_user_connections(conn, user.id)
        custom_servers = get_user_custom_servers(conn, user.id)

    user_provider_set = {ui["provider"] for ui in user_intgs}
    all_integrations = [i for i in integration_registry.list_all() if i.name != "memory"]

    my_integrations = []
    for ui_row in user_intgs:
        provider = ui_row["provider"]
        if provider == "memory":
            continue
        integration = integration_registry.get(provider)
        if not integration:
            continue
        connection = connections.get(provider)
        meta = None
        if connection and connection.get("meta_json"):
            meta = json.loads(connection["meta_json"])
        my_integrations.append({
            "name": provider,
            "display_name": integration.display_name,
            "description": integration.description,
            "is_configured": integration.is_configured(),
            "is_connected": connection is not None,
            "is_enabled": bool(ui_row["is_enabled"]),
            "meta": meta,
        })

    catalog = []
    for integration in all_integrations:
        if integration.name in user_provider_set:
            continue
        catalog.append({
            "name": integration.name,
            "display_name": integration.display_name,
            "description": integration.description,
            "is_configured": integration.is_configured(),
        })

    custom_servers_data = []
    for server in custom_servers:
        tools = json.loads(server["tools_cache_json"]) if server.get("tools_cache_json") else []
        custom_servers_data.append({
            "id": server["id"],
            "slug": server["slug"],
            "display_name": server["display_name"],
            "server_url": server["server_url"],
            "auth_type": server["auth_type"],
            "is_enabled": bool(server["is_enabled"]),
            "health_status": server["health_status"],
            "tools_count": len(tools),
            "last_health_check": server.get("last_health_check"),
        })

    return templates.TemplateResponse(
        request,
        "integrations.html",
        {
            "user": {"email": user.email, "role": user.role.value},
            "active_page": "integrations",
            "my_integrations": my_integrations,
            "catalog": catalog,
            "custom_servers": custom_servers_data,
        },
    )


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "login.html", {"user": None, "error": None})


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        request,
        "signup.html",
        {"user": None, "error": None, "success": None},
    )


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    with get_db() as conn:
        user = get_user_by_email(conn, email)

        if not user or not verify_password(password, user["password_hash"]):
            return templates.TemplateResponse(
                request,
                "login.html",
                {"user": None, "error": "Invalid email or password"},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        if user.get("status") == UserStatus.PENDING.value:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"user": None, "error": "Your signup request is still pending approval"},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        if user.get("status") == UserStatus.REJECTED.value:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"user": None, "error": "Your signup request was rejected"},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        access_token = create_access_token(
            user_id=user["id"],
            email=user["email"],
            role=user["role"],
        )

        refresh_token, refresh_expires = create_refresh_token()
        save_refresh_token(conn, user["id"], refresh_token, refresh_expires)

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,  # 7 days
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=30 * 24 * 60 * 60,
    )
    return response


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
):
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,),
        )
        if cursor.fetchone():
            return templates.TemplateResponse(
                request,
                "signup.html",
                {"user": None, "error": "User with this email already exists", "success": None},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        password_hash = hash_password(password)
        cursor = conn.execute(
            """INSERT INTO users (email, password_hash, role, status)
               VALUES (?, ?, ?, ?)""",
            (email, password_hash, UserRole.USER.value, UserStatus.PENDING.value),
        )
        conn.commit()
        new_user_id = cursor.lastrowid
        ensure_memory_integration(conn, new_user_id)

    return templates.TemplateResponse(
        request,
        "signup.html",
        {
            "user": None,
            "error": None,
            "success": "Your signup request has been submitted and is pending approval.",
        },
    )


@router.post("/logout")
async def logout_submit(request: Request):
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response


@router.post("/integrations/{name}/disconnect")
async def disconnect_integration_ui(
    name: str,
    current_user: User = Depends(get_current_user),
):
    from app.integrations.routes import delete_oauth_connection

    integration = integration_registry.get(name)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    with get_db() as conn:
        delete_oauth_connection(conn, current_user.id, name)

    provider_label = quote(integration.display_name)
    return RedirectResponse(
        url=f"/integrations?success=disconnected&provider={provider_label}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/api/dashboard/stats")
async def dashboard_stats_api(
    current_user: User = Depends(get_current_user),
    period: str = Query("7d"),
):
    if period not in ("24h", "7d", "30d", "all"):
        period = "7d"
    with get_db() as conn:
        data = _build_dashboard_stats(conn, period, user_id=current_user.id)
    return JSONResponse(content=data)


@router.get("/api/admin/dashboard/stats")
async def admin_dashboard_stats_api(
    admin: User = Depends(require_admin),
    period: str = Query("7d"),
):
    if period not in ("24h", "7d", "30d", "all"):
        period = "7d"
    with get_db() as conn:
        data = _build_dashboard_stats(conn, period, user_id=None, is_admin=True)
    return JSONResponse(content=data)


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard_page(
    request: Request,
    admin: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "user": {"email": admin.email, "role": admin.role.value},
            "active_page": "admin_dashboard",
        },
    )


@router.post("/dashboard/{provider}/add")
async def add_to_dashboard_ui(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    integration = integration_registry.get(provider)
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    with get_db() as conn:
        add_user_integration(conn, current_user.id, provider)
    return RedirectResponse(url="/integrations", status_code=status.HTTP_302_FOUND)


@router.post("/dashboard/{provider}/remove")
async def remove_from_dashboard_ui(
    provider: str,
    current_user: User = Depends(get_current_user),
):
    with get_db() as conn:
        remove_user_integration(conn, current_user.id, provider)
        delete_connection(conn, current_user.id, provider)
    return RedirectResponse(url="/integrations", status_code=status.HTTP_302_FOUND)


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    admin: User = Depends(require_admin),
):
    with get_db() as conn:
        cursor = conn.execute("SELECT * FROM users ORDER BY created_at DESC")
        users = [dict(row) for row in cursor.fetchall()]

        connections_by_user: dict[int, list[str]] = {}
        for user in users:
            connections = get_user_connections(conn, user["id"])
            connections_by_user[user["id"]] = list(connections.keys())

        for user in users:
            user["connections"] = connections_by_user.get(user["id"], [])

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": {"email": admin.email, "role": admin.role.value},
            "active_page": "users",
            "users": users,
        },
    )


@router.get("/admin/audit", response_class=HTMLResponse)
async def admin_audit_page(
    request: Request,
    admin: User = Depends(require_admin),
    user_id: Optional[int] = Query(None),
    provider: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    offset: int = Query(0),
):
    with get_db() as conn:
        cursor = conn.execute("SELECT id, email FROM users ORDER BY email")
        users = [dict(row) for row in cursor.fetchall()]

        # Build shared WHERE clause for filtered stats
        where_clauses = ["1=1"]
        where_params: list = []

        if user_id is not None:
            where_clauses.append("a.user_id = ?")
            where_params.append(user_id)

        if provider:
            where_clauses.append("a.provider = ?")
            where_params.append(provider)

        if action:
            where_clauses.append("COALESCE(a.tool_name, a.action) = ?")
            where_params.append(action)

        if status_filter:
            where_clauses.append("a.status = ?")
            where_params.append(status_filter)

        if date_from:
            where_clauses.append("a.created_at >= ?")
            where_params.append(date_from)

        if date_to:
            where_clauses.append("a.created_at <= ?")
            where_params.append(date_to + " 23:59:59")

        where_sql = " AND ".join(where_clauses)
        has_filters = len(where_params) > 0

        # Stats: recalculate based on active filters
        stats = {}
        stats["total_calls"] = conn.execute(
            f"SELECT COUNT(*) as count FROM audit_logs a WHERE {where_sql}",
            where_params,
        ).fetchone()["count"]
        stats["calls_24h"] = conn.execute(
            f"SELECT COUNT(*) as count FROM audit_logs a WHERE {where_sql} AND datetime(a.created_at) >= datetime('now', '-1 day')",
            where_params,
        ).fetchone()["count"]
        stats["unique_users"] = conn.execute(
            f"SELECT COUNT(DISTINCT a.user_id) as count FROM audit_logs a WHERE {where_sql} AND a.user_id IS NOT NULL",
            where_params,
        ).fetchone()["count"]
        stats["errors"] = conn.execute(
            f"SELECT COUNT(*) as count FROM audit_logs a WHERE {where_sql} AND a.status = 'error'",
            where_params,
        ).fetchone()["count"]
        stats["active_connections"] = conn.execute(
            "SELECT COUNT(*) as count FROM connections WHERE is_connected = 1"
        ).fetchone()["count"]
        stats["has_filters"] = has_filters

        cursor = conn.execute(
            "SELECT provider, COUNT(*) as count FROM connections WHERE is_connected = 1 GROUP BY provider ORDER BY count DESC"
        )
        connections_by_provider = [dict(row) for row in cursor.fetchall()]

        # Get distinct actions for the filter dropdown
        cursor = conn.execute(
            "SELECT DISTINCT COALESCE(tool_name, action) AS action_display FROM audit_logs ORDER BY action_display"
        )
        distinct_actions = [row["action_display"] for row in cursor.fetchall()]

        # Fetch logs
        query = f"""
            SELECT a.*, COALESCE(a.tool_name, a.action) AS action_display, u.email as user_email
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE {where_sql}
            ORDER BY a.created_at DESC LIMIT 100 OFFSET ?
        """
        log_params = list(where_params) + [offset]

        cursor = conn.execute(query, log_params)
        logs = [dict(row) for row in cursor.fetchall()]

    return templates.TemplateResponse(
        request,
        "admin/audit.html",
        {
            "user": {"email": admin.email, "role": admin.role.value},
            "active_page": "audit",
            "users": users,
            "logs": logs,
            "stats": stats,
            "connections_by_provider": connections_by_provider,
            "distinct_actions": distinct_actions,
            "filters": {
                "user_id": user_id,
                "provider": provider,
                "action": action,
                "status": status_filter,
                "date_from": date_from,
                "date_to": date_to,
                "offset": offset,
            },
        },
    )


@router.get("/admin/settings", response_class=HTMLResponse)
async def admin_settings_page(
    request: Request,
    admin: User = Depends(require_admin),
):
    settings_data = {
        "public_base_url": get_setting_value(PUBLIC_BASE_URL_KEY),
        "public_host": get_setting_value(PUBLIC_HOST_KEY),
        "teamwork_client_id": get_setting_value(TEAMWORK_CLIENT_ID_KEY),
        "teamwork_client_secret": get_setting_value(TEAMWORK_CLIENT_SECRET_KEY),
        "slack_client_id": get_setting_value(SLACK_CLIENT_ID_KEY),
        "slack_client_secret": get_setting_value(SLACK_CLIENT_SECRET_KEY),
        "miro_client_id": get_setting_value(MIRO_CLIENT_ID_KEY),
        "miro_client_secret": get_setting_value(MIRO_CLIENT_SECRET_KEY),
        "figma_client_id": get_setting_value(FIGMA_CLIENT_ID_KEY),
        "figma_client_secret": get_setting_value(FIGMA_CLIENT_SECRET_KEY),
        "telegram_api_id": get_setting_value(TELEGRAM_API_ID_KEY),
        "telegram_api_hash": get_setting_value(TELEGRAM_API_HASH_KEY),
    }

    from app.config.store import get_public_base_url
    base_url = get_public_base_url()

    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "user": {"email": admin.email, "role": admin.role.value},
            "active_page": "settings",
            "settings": settings_data,
            "base_url": base_url,
        },
    )


@router.get("/memory", response_class=HTMLResponse)
async def memory_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    q: Optional[str] = Query(None),
):
    from app.integrations.memory import store as memory_store

    with get_db() as conn:
        total = memory_store.count_items(conn, current_user.id)

        if q and q.strip():
            items = memory_store.search_items(conn, current_user.id, q.strip(), top_k=100)
        else:
            items = memory_store.list_items(conn, current_user.id, limit=200)

        context_pack = memory_store.get_context_pack(conn, current_user.id)

    return templates.TemplateResponse(
        request,
        "memory.html",
        {
            "user": {"email": current_user.email, "role": current_user.role.value},
            "active_page": "memory",
            "items": items,
            "total": total,
            "context_pack": context_pack,
            "search_query": q or "",
        },
    )


@router.post("/memory/upsert")
async def memory_upsert(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    from app.integrations.memory import store as memory_store
    from app.integrations.memory.evaluate import evaluate_write

    form = await request.form()
    item_data = {
        "title": form.get("title", ""),
        "type": form.get("type", "note"),
        "scope": form.get("scope", "global"),
        "value_json": form.get("value_json", "{}"),
        "tags_json": [t.strip() for t in form.get("tags", "").split(",") if t.strip()],
        "pinned": form.get("pinned") == "on",
        "sensitivity": form.get("sensitivity", "low"),
        "explicit": True,
    }

    ttl_value = form.get("ttl_days", "")
    if ttl_value and ttl_value != "null":
        item_data["ttl_days"] = int(ttl_value)

    eval_result = evaluate_write(item_data)
    if eval_result["allow"]:
        item_data["ttl_days"] = eval_result.get("ttl_days", item_data.get("ttl_days"))
        item_data["sensitivity"] = eval_result.get("sensitivity", item_data.get("sensitivity"))

    with get_db() as conn:
        memory_store.upsert_item(conn, current_user.id, item_data)

    return RedirectResponse(url="/memory", status_code=status.HTTP_302_FOUND)


@router.post("/memory/{item_id}/delete")
async def memory_delete(
    item_id: str,
    current_user: User = Depends(get_current_user),
):
    from app.integrations.memory import store as memory_store

    with get_db() as conn:
        memory_store.delete_item(conn, current_user.id, item_id)

    return RedirectResponse(url="/memory", status_code=status.HTTP_302_FOUND)


@router.post("/memory/{item_id}/pin")
async def memory_pin(
    item_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    from app.integrations.memory import store as memory_store

    form = await request.form()
    pinned = form.get("pinned") == "true"

    with get_db() as conn:
        memory_store.pin_item(conn, current_user.id, item_id, pinned)

    return RedirectResponse(url="/memory", status_code=status.HTTP_302_FOUND)


@router.post("/memory/{item_id}/ttl")
async def memory_set_ttl(
    item_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    from app.integrations.memory import store as memory_store

    form = await request.form()
    ttl_value = form.get("ttl_days")
    ttl_days = int(ttl_value) if ttl_value and ttl_value != "null" else None

    with get_db() as conn:
        memory_store.set_ttl(conn, current_user.id, item_id, ttl_days)

    return RedirectResponse(url="/memory", status_code=status.HTTP_302_FOUND)


@router.get("/account", response_class=HTMLResponse)
async def account_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "account.html",
        {
            "user": {"email": current_user.email, "role": current_user.role.value},
            "active_page": "account",
        },
    )
