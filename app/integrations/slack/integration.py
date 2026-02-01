from typing import Optional

from app.integrations.base import BaseIntegration, ToolDefinition, ToolResult
from app.integrations.slack import oauth, tools
from app.config.store import get_integration_credentials


class SlackIntegration(BaseIntegration):
    name = "slack"
    display_name = "Slack"
    description = "Team communication and collaboration platform"

    def is_configured(self) -> bool:
        client_id, client_secret = get_integration_credentials("slack")
        return bool(client_id and client_secret)

    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        return oauth.get_oauth_start_url(state, redirect_uri)

    async def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        token_data = await oauth.exchange_code_for_token(code, redirect_uri)

        team = token_data.get("team", {})
        authed_user = token_data.get("authed_user", {})
        meta = {
            "team_id": team.get("id"),
            "team_name": team.get("name"),
            "user_id": authed_user.get("id"),
        }

        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "meta": meta,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        return await oauth.refresh_access_token(refresh_token)

    def get_tools(self) -> list[ToolDefinition]:
        return tools.SLACK_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        access_token: str,
        meta: Optional[dict] = None,
    ) -> ToolResult:
        return await tools.execute_tool(tool_name, args, access_token, meta)
