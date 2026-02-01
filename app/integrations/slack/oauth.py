from urllib.parse import urlencode
import httpx

from app.config.store import get_integration_credentials


SLACK_AUTH_URL = "https://slack.com/oauth/v2/authorize"
SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"

SLACK_SCOPES = [
    "channels:read",
    "channels:history",
    "chat:write",
    "search:read",
    "users:read",
]


def get_oauth_start_url(state: str, redirect_uri: str) -> str:
    client_id, _ = get_integration_credentials("slack")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": ",".join(SLACK_SCOPES),
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

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "team": data.get("team", {}),
            "authed_user": data.get("authed_user", {}),
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
