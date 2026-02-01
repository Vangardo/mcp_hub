from typing import Optional
from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.slack.client import SlackClient


SLACK_TOOLS = [
    ToolDefinition(
        name="slack.channels.list",
        description="List all channels in Slack workspace",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max channels to return", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
                "types": {
                    "type": "string",
                    "description": "Channel types (comma-separated)",
                    "default": "public_channel,private_channel",
                },
            },
        },
    ),
    ToolDefinition(
        name="slack.users.list",
        description="List all users in Slack workspace",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max users to return", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
        },
    ),
    ToolDefinition(
        name="slack.messages.post",
        description="Post a message to a Slack channel",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel ID or name"},
                "text": {"type": "string", "description": "Message text"},
                "thread_ts": {"type": "string", "description": "Thread timestamp for replies"},
            },
            "required": ["channel", "text"],
        },
    ),
    ToolDefinition(
        name="slack.messages.search",
        description="Search for messages in Slack",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "count": {"type": "integer", "description": "Number of results", "default": 20},
                "page": {"type": "integer", "description": "Page number", "default": 1},
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="slack.messages.history",
        description="Get message history for a Slack channel",
        input_schema={
            "type": "object",
            "properties": {
                "channel": {"type": "string", "description": "Channel ID"},
                "limit": {"type": "integer", "description": "Max messages to return", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
            "required": ["channel"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    client = SlackClient(access_token)

    try:
        if tool_name == "slack.channels.list":
            result = await client.list_channels(
                limit=args.get("limit", 100),
                cursor=args.get("cursor"),
                types=args.get("types", "public_channel,private_channel"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.users.list":
            result = await client.list_users(
                limit=args.get("limit", 100),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.messages.post":
            result = await client.post_message(
                channel=args["channel"],
                text=args["text"],
                thread_ts=args.get("thread_ts"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.messages.search":
            result = await client.search_messages(
                query=args["query"],
                count=args.get("count", 20),
                page=args.get("page", 1),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.messages.history":
            result = await client.get_channel_history(
                channel=args["channel"],
                limit=args.get("limit", 100),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
