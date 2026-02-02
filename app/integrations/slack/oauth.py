from urllib.parse import urlencode
import httpx

from app.config.store import get_integration_credentials


SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

# User scopes - действия от имени пользователя
# Эти scopes должны совпадать с настройками в Slack App
SLACK_USER_SCOPES = [
    # Channels - публичные
    "channels:read",
    "channels:history",
    # Groups - приватные каналы
    "groups:read",
    "groups:history",
    # Chat
    "chat:write",
    # Direct Messages (1:1)
    "im:read",
    "im:write",
    "im:history",
    # Group DMs (multi-person)
    "mpim:read",
    "mpim:write",
    "mpim:history",
    # Users
    "users:read",
    "users:read.email",
    # Search
    "search:read.public",   # публичные каналы
    "search:read.files",    # файлы
    "search:read.users",    # пользователи
    # Canvas
    "canvases:read",
    "canvases:write",
]


def get_oauth_start_url(state: str, redirect_uri: str) -> str:
    client_id, _ = get_integration_credentials("slack")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": "",  # Пустой - бот не нужен
        "user_scope": ",".join(SLACK_USER_SCOPES),
    }
    return f"{SLACK_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = get_integration_credentials("slack")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SLACK_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            raise ValueError(f"Slack OAuth error: {data.get('error')}")

        # User token flow - токен в authed_user
        authed_user = data.get("authed_user", {})

        return {
            "access_token": authed_user.get("access_token") or data.get("access_token"),
            "refresh_token": authed_user.get("refresh_token") or data.get("refresh_token"),
            "team": data.get("team", {}),
            "authed_user": authed_user,
        }


async def refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret = get_integration_credentials("slack")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SLACK_TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            raise ValueError(f"Slack token refresh error: {data.get('error')}")

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
        }
