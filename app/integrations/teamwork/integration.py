from typing import Optional
import json

from app.integrations.base import BaseIntegration, ToolDefinition, ToolResult
from app.integrations.teamwork import oauth, tools
from app.config.store import get_integration_credentials


class TeamworkIntegration(BaseIntegration):
    name = "teamwork"
    display_name = "Teamwork"
    description = "Project management and team collaboration platform"

    def is_configured(self) -> bool:
        client_id, client_secret = get_integration_credentials("teamwork")
        return bool(client_id and client_secret)

    def get_oauth_start_url(self, state: str, redirect_uri: str) -> str:
        return oauth.get_oauth_start_url(state, redirect_uri)

    async def handle_oauth_callback(self, code: str, redirect_uri: str) -> dict:
        token_data = await oauth.exchange_code_for_token(code, redirect_uri)

        installation = token_data.get("installation", {})
        meta = {
            "site_url": installation.get("apiEndPoint", ""),
            "company_name": installation.get("name", ""),
            "company_id": installation.get("id"),
        }
        try:
            from app.integrations.teamwork.client import TeamworkClient
            client = TeamworkClient(token_data["access_token"], meta["site_url"])
            me = await client.get_current_user()
            person = me.get("person") if isinstance(me, dict) else None
            if isinstance(person, dict):
                meta.update(
                    {
                        "user_id": person.get("id"),
                        "first_name": person.get("first-name"),
                        "last_name": person.get("last-name"),
                        "email": person.get("email-address"),
                        "user_name": person.get("user-name"),
                    }
                )
        except Exception:
            pass

        return {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_in": token_data.get("expires_in"),
            "meta": meta,
        }

    async def refresh_access_token(self, refresh_token: str) -> dict:
        return await oauth.refresh_access_token(refresh_token)

    def get_tools(self) -> list[ToolDefinition]:
        return tools.TEAMWORK_TOOLS

    async def execute_tool(
        self,
        tool_name: str,
        args: dict,
        access_token: str,
        meta: Optional[dict] = None,
    ) -> ToolResult:
        return await tools.execute_tool(tool_name, args, access_token, meta)
