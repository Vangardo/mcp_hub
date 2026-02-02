"""
OAuth 2.0 Authorization Server for MCP clients (like ChatGPT).
Implements OAuth 2.1 with PKCE as required by MCP specification.
"""
import secrets
import hashlib
import base64
import time
from urllib.parse import urlencode, parse_qs
from typing import Optional

from fastapi import APIRouter, Request, HTTPException, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)

from app.settings import settings
from app.db import get_db
from app.auth.hashing import verify_password
from app.auth.jwt import create_access_token


oauth_server_router = APIRouter(tags=["oauth-server"])

# In-memory storage for authorization codes and PKCE challenges
# In production, use Redis or database
_auth_codes: dict[str, dict] = {}
_pkce_challenges: dict[str, dict] = {}


# Storage for dynamically registered clients
_registered_clients: dict[str, dict] = {}


class OAuthMetadata(BaseModel):
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str  # RFC 7591
    response_types_supported: list[str] = ["code"]
    grant_types_supported: list[str] = ["authorization_code", "refresh_token"]
    code_challenge_methods_supported: list[str] = ["S256", "plain"]
    token_endpoint_auth_methods_supported: list[str] = ["none", "client_secret_post", "client_secret_basic"]
    scopes_supported: list[str] = ["mcp", "openid", "profile", "email"]


class ProtectedResourceMetadata(BaseModel):
    resource: str
    authorization_servers: list[str]
    scopes_supported: list[str] = ["mcp"]
    bearer_methods_supported: list[str] = ["header"]


@oauth_server_router.get("/.well-known/oauth-protected-resource")
@oauth_server_router.get("/.well-known/oauth-protected-resource/{path:path}")
async def protected_resource_metadata(request: Request):
    """OAuth 2.0 Protected Resource Metadata (RFC 9728)"""
    # Force HTTPS for production
    base_url = str(request.base_url).rstrip("/")
    if base_url.startswith("http://") and "localhost" not in base_url:
        base_url = base_url.replace("http://", "https://", 1)

    metadata = ProtectedResourceMetadata(
        resource=f"{base_url}/mcp",
        authorization_servers=[base_url],
    )

    return metadata.model_dump()


@oauth_server_router.get("/.well-known/openid-configuration")
@oauth_server_router.get("/.well-known/openid-configuration/{path:path}")
@oauth_server_router.get("/mcp/.well-known/openid-configuration")
async def openid_configuration(request: Request):
    """OpenID Connect Discovery - redirects to OAuth metadata"""
    return await oauth_metadata(request)


@oauth_server_router.get("/.well-known/oauth-authorization-server")
@oauth_server_router.get("/.well-known/oauth-authorization-server/{path:path}")
@oauth_server_router.get("/mcp/.well-known/oauth-authorization-server")
async def oauth_metadata(request: Request):
    """OAuth 2.0 Authorization Server Metadata (RFC 8414)"""
    # Force HTTPS for production
    base_url = str(request.base_url).rstrip("/")
    if base_url.startswith("http://") and "localhost" not in base_url:
        base_url = base_url.replace("http://", "https://", 1)

    metadata = OAuthMetadata(
        issuer=base_url,
        authorization_endpoint=f"{base_url}/oauth/authorize",
        token_endpoint=f"{base_url}/oauth/token",
        registration_endpoint=f"{base_url}/oauth/register",
    )

    return metadata.model_dump()


@oauth_server_router.post("/oauth/register")
async def register_client(request: Request):
    """OAuth 2.0 Dynamic Client Registration (RFC 7591)"""
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Generate client credentials
    client_id = secrets.token_urlsafe(24)
    client_secret = secrets.token_urlsafe(32)

    # Extract client metadata
    redirect_uris = body.get("redirect_uris", [])
    client_name = body.get("client_name", "Unknown Client")
    client_uri = body.get("client_uri", "")
    grant_types = body.get("grant_types", ["authorization_code"])
    response_types = body.get("response_types", ["code"])
    token_endpoint_auth_method = body.get("token_endpoint_auth_method", "client_secret_post")

    # Store client registration
    _registered_clients[client_id] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uris": redirect_uris,
        "client_name": client_name,
        "client_uri": client_uri,
        "grant_types": grant_types,
        "response_types": response_types,
        "token_endpoint_auth_method": token_endpoint_auth_method,
        "created_at": time.time(),
    }

    # Return client credentials (RFC 7591 response)
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "client_id_issued_at": int(time.time()),
        "client_secret_expires_at": 0,  # Never expires
        "redirect_uris": redirect_uris,
        "client_name": client_name,
        "client_uri": client_uri,
        "grant_types": grant_types,
        "response_types": response_types,
        "token_endpoint_auth_method": token_endpoint_auth_method,
    }


@oauth_server_router.get("/oauth/authorize")
async def authorize_get(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    state: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
    scope: Optional[str] = None,
):
    """OAuth 2.0 Authorization Endpoint - show login form"""

    if response_type != "code":
        return JSONResponse(
            {"error": "unsupported_response_type"},
            status_code=400
        )

    # Store PKCE challenge
    session_id = secrets.token_urlsafe(32)
    _pkce_challenges[session_id] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
        "scope": scope,
        "created_at": time.time(),
    }

    # Simple login form
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCP Hub - Authorize</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 20px;
                box-sizing: border-box;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 40px;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            h1 {{
                margin: 0 0 8px 0;
                color: #1a1a2e;
                font-size: 24px;
            }}
            .subtitle {{
                color: #666;
                margin-bottom: 30px;
                font-size: 14px;
            }}
            .client-info {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 24px;
                font-size: 13px;
                color: #555;
            }}
            label {{
                display: block;
                margin-bottom: 6px;
                font-weight: 500;
                color: #333;
            }}
            input[type="email"],
            input[type="password"] {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 16px;
                margin-bottom: 16px;
                box-sizing: border-box;
                transition: border-color 0.2s;
            }}
            input:focus {{
                outline: none;
                border-color: #667eea;
            }}
            button {{
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }}
            button:hover {{
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
            }}
            .error {{
                background: #fee;
                color: #c00;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 16px;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>MCP Hub</h1>
            <p class="subtitle">Authorize application access</p>

            <div class="client-info">
                <strong>{client_id}</strong> wants to access your MCP Hub account
            </div>

            <form method="POST" action="/oauth/authorize">
                <input type="hidden" name="session_id" value="{session_id}">

                <label for="email">Email</label>
                <input type="email" id="email" name="email" required autocomplete="email">

                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">

                <button type="submit">Authorize</button>
            </form>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(html)


@oauth_server_router.post("/oauth/authorize")
async def authorize_post(
    session_id: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    """OAuth 2.0 Authorization Endpoint - process login"""
    print(f"[OAUTH] Authorize POST: email={email}, session_id={session_id[:10]}...")

    # Get PKCE challenge data
    challenge_data = _pkce_challenges.pop(session_id, None)
    if not challenge_data:
        raise HTTPException(status_code=400, detail="Invalid or expired session")

    # Check if session is expired (10 minutes)
    if time.time() - challenge_data["created_at"] > 600:
        raise HTTPException(status_code=400, detail="Session expired")

    # Verify user credentials
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, email, password_hash, role, status FROM users WHERE email = ?",
            (email,)
        )
        user = cursor.fetchone()

    if not user:
        # Re-show form with error
        return await _show_auth_error(challenge_data, "Invalid email or password")

    if not verify_password(password, user["password_hash"]):
        return await _show_auth_error(challenge_data, "Invalid email or password")

    if user["status"] != "approved":
        return await _show_auth_error(challenge_data, "Account not approved")

    # Generate authorization code
    auth_code = secrets.token_urlsafe(32)
    _auth_codes[auth_code] = {
        "user_id": user["id"],
        "user_email": user["email"],
        "user_role": user["role"],
        "client_id": challenge_data["client_id"],
        "redirect_uri": challenge_data["redirect_uri"],
        "code_challenge": challenge_data["code_challenge"],
        "code_challenge_method": challenge_data["code_challenge_method"],
        "scope": challenge_data["scope"],
        "created_at": time.time(),
    }

    # Redirect back to client
    redirect_params = {"code": auth_code}
    if challenge_data["state"]:
        redirect_params["state"] = challenge_data["state"]

    redirect_url = f"{challenge_data['redirect_uri']}?{urlencode(redirect_params)}"
    print(f"[OAUTH] Redirect to: {redirect_url}")
    print(f"[OAUTH] Auth code: {auth_code}")
    return RedirectResponse(redirect_url, status_code=302)


async def _show_auth_error(challenge_data: dict, error_message: str):
    """Re-show authorization form with error"""
    session_id = secrets.token_urlsafe(32)
    _pkce_challenges[session_id] = {
        **challenge_data,
        "created_at": time.time(),
    }

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MCP Hub - Authorize</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                padding: 20px;
                box-sizing: border-box;
            }}
            .card {{
                background: white;
                border-radius: 16px;
                padding: 40px;
                max-width: 400px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }}
            h1 {{ margin: 0 0 8px 0; color: #1a1a2e; font-size: 24px; }}
            .subtitle {{ color: #666; margin-bottom: 30px; font-size: 14px; }}
            .client-info {{
                background: #f8f9fa;
                border-radius: 8px;
                padding: 12px;
                margin-bottom: 24px;
                font-size: 13px;
                color: #555;
            }}
            label {{ display: block; margin-bottom: 6px; font-weight: 500; color: #333; }}
            input[type="email"], input[type="password"] {{
                width: 100%;
                padding: 12px;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                font-size: 16px;
                margin-bottom: 16px;
                box-sizing: border-box;
            }}
            input:focus {{ outline: none; border-color: #667eea; }}
            button {{
                width: 100%;
                padding: 14px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
            }}
            .error {{
                background: #fee;
                color: #c00;
                padding: 12px;
                border-radius: 8px;
                margin-bottom: 16px;
                font-size: 14px;
            }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>MCP Hub</h1>
            <p class="subtitle">Authorize application access</p>

            <div class="error">{error_message}</div>

            <div class="client-info">
                <strong>{challenge_data['client_id']}</strong> wants to access your MCP Hub account
            </div>

            <form method="POST" action="/oauth/authorize">
                <input type="hidden" name="session_id" value="{session_id}">

                <label for="email">Email</label>
                <input type="email" id="email" name="email" required>

                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>

                <button type="submit">Authorize</button>
            </form>
        </div>
    </body>
    </html>
    """

    return HTMLResponse(html)


def _verify_pkce(code_verifier: str, code_challenge: str, method: str) -> bool:
    """Verify PKCE code_verifier against stored code_challenge"""
    if method == "S256":
        # SHA256 hash of verifier, base64url encoded
        digest = hashlib.sha256(code_verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return computed == code_challenge
    elif method == "plain":
        return code_verifier == code_challenge
    return False


# Token endpoint moved to app/auth/routes.py to avoid route conflicts


# Cleanup old codes periodically (call from background task if needed)
def cleanup_expired_codes():
    """Remove expired authorization codes and PKCE challenges"""
    now = time.time()
    expired_codes = [k for k, v in _auth_codes.items() if now - v["created_at"] > 600]
    for k in expired_codes:
        _auth_codes.pop(k, None)

    expired_challenges = [k for k, v in _pkce_challenges.items() if now - v["created_at"] > 600]
    for k in expired_challenges:
        _pkce_challenges.pop(k, None)
