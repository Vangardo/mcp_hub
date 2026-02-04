from typing import Optional

from app.integrations.base import BaseIntegration, ToolDefinition, ToolResult
from app.integrations.figma import oauth, tools
from app.config.store import get_integration_credentials


class FigmaIntegration(BaseIntegration):
    name = "figma"
    display_name = "Figma"
    description = "Design and prototyping platform"

    def is_configured(self) -> bool:
        client_id, client_secret = get_integration_credentials("figma")
        return bool(client_id and client_secret)

    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        return oauth.get_oauth_start_url(state, redirect_uri)

    async def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        token_data = await oauth.exchange_code_for_token(code, redirect_uri)

        access_token = token_data["access_token"]

        meta = {}
        try:
            from app.integrations.figma.client import FigmaClient
            client = FigmaClient(access_token)
            user_info = await client.get_me()
            meta = {
                "user_id": str(user_info.get("id", "")),
                "handle": user_info.get("handle", ""),
                "email": user_info.get("email", ""),
                "img_url": user_info.get("img_url", ""),
            }
        except Exception:
            pass

        return {
            "access_token": access_token,
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "meta": meta,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        return await oauth.refresh_access_token(refresh_token)

    def get_tools(self) -> list[ToolDefinition]:
        return tools.FIGMA_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        access_token: str,
        meta: Optional[dict] = None,
    ) -> ToolResult:
        return await tools.execute_tool(tool_name, args, access_token, meta)
