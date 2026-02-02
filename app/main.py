from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

from app.settings import settings
from app.db import init_db, get_db
from app.auth.hashing import hash_password
from app.auth.routes import router as auth_router, oauth_router as oauth_auth_router
from app.integrations.routes import router as integrations_router, oauth_router
from app.integrations.registry import register_integrations
from app.mcp_gateway import mcp_router
from app.mcp_gateway.oauth_server import oauth_server_router
from app.admin import admin_router
from app.config import config_router
from app.ui import ui_router


def create_admin_user():
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id FROM users WHERE email = ?",
            (settings.admin_email,)
        )
        if cursor.fetchone():
            return

        password_hash = hash_password(settings.admin_password)
        conn.execute(
            "INSERT INTO users (email, password_hash, role, status) VALUES (?, ?, ?, ?)",
            (settings.admin_email, password_hash, "admin", "approved")
        )
        conn.commit()
        print(f"Admin user created: {settings.admin_email}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    register_integrations()
    create_admin_user()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for OAuth and MCP endpoints (ChatGPT, Claude, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

static_path = Path(__file__).parent / "ui" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

app.include_router(auth_router)
app.include_router(oauth_auth_router)
app.include_router(integrations_router)
app.include_router(oauth_router)
app.include_router(mcp_router)
app.include_router(oauth_server_router)
app.include_router(admin_router)
app.include_router(config_router)
app.include_router(ui_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
