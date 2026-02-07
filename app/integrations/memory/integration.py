from typing import Optional

from app.integrations.base import BaseIntegration, ToolDefinition, ToolResult
from app.integrations.memory import tools


class MemoryIntegration(BaseIntegration):
    name = "memory"
    display_name = "Memory"
    description = "Persistent memory for AI context — preferences, goals, watchlists"
    auth_type = "internal"

    def is_configured(self) -> bool:
        return True  # Always available, no config needed

    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        raise NotImplementedError("Memory is a built-in provider, no OAuth")

    async def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        raise NotImplementedError("Memory is a built-in provider, no OAuth")

    async def refresh_access_token(self, refresh_token: str) -> dict:
        raise NotImplementedError("Memory is a built-in provider, no tokens")

    def get_tools(self) -> list[ToolDefinition]:
        return tools.MEMORY_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        access_token: str,
        meta: Optional[dict] = None,
    ) -> ToolResult:
        return await tools.execute_tool(tool_name, args, access_token, meta)
