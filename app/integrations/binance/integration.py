from typing import Optional

from app.integrations.base import BaseIntegration, ToolDefinition, ToolResult
from app.integrations.binance import tools


class BinanceIntegration(BaseIntegration):
    name = "binance"
    display_name = "Binance"
    description = "Cryptocurrency exchange — spot trading & market analysis"
    auth_type = "pat"

    def is_configured(self) -> bool:
        return True  # No admin config needed — users connect via API key

    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Binance uses API keys, not OAuth")

    async def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        raise NotImplementedError("Binance uses API keys, not OAuth")

    async def refresh_access_token(self, refresh_token: str) -> dict:
        raise NotImplementedError("Binance API keys don't expire")

    def get_tools(self) -> list[ToolDefinition]:
        return tools.BINANCE_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        access_token: str,
        meta: Optional[dict] = None,
    ) -> ToolResult:
        return await tools.execute_tool(tool_name, args, access_token, meta)
