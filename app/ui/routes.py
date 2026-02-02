from typing import Optional
import json
import os

from fastapi import APIRouter, Request, Depends, Form, HTTPException, status, Query
from fastapi.responses import HTMLResponse, RedirectResponse
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
    TELEGRAM_API_ID_KEY,
    TELEGRAM_API_HASH_KEY,
    get_setting_value,
)
from app.integrations.connections import get_user_connections


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


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, user: Optional[User] = Depends(get_current_user_optional)):
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    integrations = integration_registry.list_all()

    with get_db() as conn:
        connections = get_user_connections(conn, user.id)

    integration_data = []
    for integration in integrations:
        connection = connections.get(integration.name)
        meta = None
        if connection and connection.get("meta_json"):
            meta = json.loads(connection["meta_json"])

        integration_data.append({
            "name": integration.name,
            "display_name": integration.display_name,
            "description": integration.description,
            "is_configured": integration.is_configured(),
            "is_connected": connection is not None,
            "meta": meta,
        })

    return templates.TemplateResponse(
        request,
        "integrations.html",
        {
            "user": {"email": user.email, "role": user.role.value},
            "active_page": "integrations",
            "integrations": integration_data,
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
        conn.execute(
            """INSERT INTO users (email, password_hash, role, status)
               VALUES (?, ?, ?, ?)""",
            (email, password_hash, UserRole.USER.value, UserStatus.PENDING.value),
        )
        conn.commit()

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

    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


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
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    offset: int = Query(0),
):
    with get_db() as conn:
        cursor = conn.execute("SELECT id, email FROM users ORDER BY email")
        users = [dict(row) for row in cursor.fetchall()]

        stats = {}
        stats["total_calls"] = conn.execute(
            "SELECT COUNT(*) as count FROM audit_logs"
        ).fetchone()["count"]
        stats["calls_24h"] = conn.execute(
            "SELECT COUNT(*) as count FROM audit_logs WHERE datetime(created_at) >= datetime('now', '-1 day')"
        ).fetchone()["count"]
        stats["unique_users"] = conn.execute(
            "SELECT COUNT(DISTINCT user_id) as count FROM audit_logs WHERE user_id IS NOT NULL"
        ).fetchone()["count"]
        stats["active_users"] = conn.execute(
            "SELECT COUNT(*) as count FROM users WHERE is_active = 1 AND status = ?",
            (UserStatus.APPROVED.value,),
        ).fetchone()["count"]
        stats["active_connections"] = conn.execute(
            "SELECT COUNT(*) as count FROM connections WHERE is_connected = 1"
        ).fetchone()["count"]

        cursor = conn.execute(
            "SELECT provider, COUNT(*) as count FROM connections WHERE is_connected = 1 GROUP BY provider ORDER BY count DESC"
        )
        connections_by_provider = [dict(row) for row in cursor.fetchall()]

        query = """
            SELECT a.*, u.email as user_email
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE 1=1
        """
        params: list = []

        if user_id is not None:
            query += " AND a.user_id = ?"
            params.append(user_id)

        if provider:
            query += " AND a.provider = ?"
            params.append(provider)

        if date_from:
            query += " AND a.created_at >= ?"
            params.append(date_from)

        if date_to:
            query += " AND a.created_at <= ?"
            params.append(date_to + " 23:59:59")

        query += " ORDER BY a.created_at DESC LIMIT 100 OFFSET ?"
        params.append(offset)

        cursor = conn.execute(query, params)
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
            "filters": {
                "user_id": user_id,
                "provider": provider,
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
        "telegram_api_id": get_setting_value(TELEGRAM_API_ID_KEY),
        "telegram_api_hash": get_setting_value(TELEGRAM_API_HASH_KEY),
    }

    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "user": {"email": admin.email, "role": admin.role.value},
            "active_page": "settings",
            "settings": settings_data,
        },
    )


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
