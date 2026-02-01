from typing import Optional

from app.integrations.base import BaseIntegration, ToolDefinition, ToolResult
from app.integrations.telegram import tools
from app.config.store import get_telegram_api_credentials


class TelegramIntegration(BaseIntegration):
    name = "telegram"
    display_name = "Telegram"
    description = "Telegram messaging via MTProto user session"
    auth_type = "session"

    def is_configured(self) -> bool:
        api_id, api_hash = get_telegram_api_credentials()
        return bool(api_id and api_hash)

    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Telegram uses session-based login")

    async def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        raise NotImplementedError("Telegram uses session-based login")

    async def refresh_access_token(self, refresh_token: str) -> dict:
        raise NotImplementedError("Telegram sessions do not refresh via OAuth")

    def get_tools(self) -> list[ToolDefinition]:
        return tools.TELEGRAM_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        access_token: str,
        meta: Optional[dict] = None,
    ) -> ToolResult:
        return await tools.execute_tool(tool_name, args, access_token, meta)
