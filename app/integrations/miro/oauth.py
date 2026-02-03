from urllib.parse import urlencode

import httpx

from app.config.store import get_integration_credentials


MIRO_AUTH_URL = "https://miro.com/oauth/authorize"
MIRO_TOKEN_URL = "https://api.miro.com/v1/oauth/token"

MIRO_SCOPES = [
    "boards:read",
    "boards:write",
    "identity:read",
    "team:read",
]


def get_oauth_start_url(state: str, redirect_uri: str) -> str:
    client_id, _ = get_integration_credentials("miro")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{MIRO_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str, redirect_uri: str) -> dict:
    client_id, client_secret = get_integration_credentials("miro")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            MIRO_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "access_token" not in data:
            raise ValueError(f"Miro OAuth error: {data.get('error', 'no access_token')}")

        return data


async def refresh_access_token(refresh_token: str) -> dict:
    client_id, client_secret = get_integration_credentials("miro")
    async with httpx.AsyncClient() as client:
        response = await client.post(
            MIRO_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
        )
        response.raise_for_status()
        data = response.json()

        if "access_token" not in data:
            raise ValueError(f"Miro token refresh error: {data.get('error', 'no access_token')}")

        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in"),
        }
