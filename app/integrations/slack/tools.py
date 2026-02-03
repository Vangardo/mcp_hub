from typing import Optional
from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.slack.client import SlackClient


SLACK_TOOLS = [
    ToolDefinition(
        name="slack.channels.list",
        description="List all channels in Slack workspace. Returns channel IDs and names needed for posting messages and getting history.",
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
        description="List all users in Slack workspace. Returns user IDs needed for sending DMs, finding users, and sharing canvases.",
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
    # === DIRECT MESSAGES ===
    ToolDefinition(
        name="slack.dm.list",
        description="List all direct message conversations (1:1 DMs with users)",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max DMs to return", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
        },
    ),
    ToolDefinition(
        name="slack.dm.group_list",
        description="List all group direct messages (multi-person DMs)",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max group DMs to return", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
        },
    ),
    ToolDefinition(
        name="slack.dm.send",
        description="Send a direct message to a user by their user ID",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID to send DM to"},
                "text": {"type": "string", "description": "Message text"},
                "thread_ts": {"type": "string", "description": "Thread timestamp for replies"},
            },
            "required": ["user_id", "text"],
        },
    ),
    ToolDefinition(
        name="slack.dm.history",
        description="Get DM history with a specific user",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID"},
                "limit": {"type": "integer", "description": "Max messages to return", "default": 100},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
            "required": ["user_id"],
        },
    ),
    ToolDefinition(
        name="slack.dm.open",
        description="Open/get a DM conversation with a user (returns channel ID)",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID"},
            },
            "required": ["user_id"],
        },
    ),
    ToolDefinition(
        name="slack.dm.open_group",
        description="Open/get a group DM with multiple users",
        input_schema={
            "type": "object",
            "properties": {
                "user_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of user IDs",
                },
            },
            "required": ["user_ids"],
        },
    ),
    # === USER LOOKUP ===
    ToolDefinition(
        name="slack.users.find_by_email",
        description="Find a Slack user by their email address",
        input_schema={
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "User's email address"},
            },
            "required": ["email"],
        },
    ),
    ToolDefinition(
        name="slack.users.info",
        description="Get detailed info about a user",
        input_schema={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID"},
            },
            "required": ["user_id"],
        },
    ),
    # === CANVAS ===
    ToolDefinition(
        name="slack.canvas.create",
        description="Create a new Slack canvas (collaborative document). Returns canvas_id for further operations like editing, sharing, or looking up sections.",
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Canvas title"},
                "markdown": {"type": "string", "description": "Initial content in markdown format"},
            },
            "required": ["title"],
        },
    ),
    ToolDefinition(
        name="slack.canvas.edit",
        description="Edit content in a Slack canvas. Use 'replace' to overwrite all content, 'insert_at_end' to append, 'insert_at_start' to prepend. Content is in markdown format.",
        input_schema={
            "type": "object",
            "properties": {
                "canvas_id": {"type": "string", "description": "Canvas ID"},
                "markdown": {"type": "string", "description": "Markdown content to append"},
                "operation": {
                    "type": "string",
                    "description": "Operation type",
                    "enum": ["insert_at_end", "insert_at_start", "replace"],
                    "default": "insert_at_end",
                },
            },
            "required": ["canvas_id", "markdown"],
        },
    ),
    ToolDefinition(
        name="slack.canvas.delete",
        description="Delete a Slack canvas",
        input_schema={
            "type": "object",
            "properties": {
                "canvas_id": {"type": "string", "description": "Canvas ID"},
            },
            "required": ["canvas_id"],
        },
    ),
    ToolDefinition(
        name="slack.canvas.share",
        description="Share a canvas with users or channels. Set access_level to 'read' for view-only or 'write' for editing permissions.",
        input_schema={
            "type": "object",
            "properties": {
                "canvas_id": {"type": "string", "description": "Canvas ID"},
                "access_level": {
                    "type": "string",
                    "description": "Access level",
                    "enum": ["read", "write"],
                    "default": "read",
                },
                "channel_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Channel IDs to share with",
                },
                "user_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "User IDs to share with",
                },
            },
            "required": ["canvas_id"],
        },
    ),
    ToolDefinition(
        name="slack.canvas.sections_lookup",
        description="Find sections in a Slack canvas by heading type or text content. Use this to read canvas content and get section IDs for targeted editing. Sections can be filtered by heading level (h1, h2) or by text they contain.",
        input_schema={
            "type": "object",
            "properties": {
                "canvas_id": {"type": "string", "description": "Canvas ID"},
                "section_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Filter by section type: 'h1', 'h2', or 'any_header'",
                },
                "contains_text": {
                    "type": "string",
                    "description": "Filter sections containing this text",
                },
            },
            "required": ["canvas_id"],
        },
    ),
    ToolDefinition(
        name="slack.canvas.access_list",
        description="List who has access to a Slack canvas. Returns users and channels with their access levels (read/write).",
        input_schema={
            "type": "object",
            "properties": {
                "canvas_id": {"type": "string", "description": "Canvas ID"},
            },
            "required": ["canvas_id"],
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

        # === DIRECT MESSAGES ===
        elif tool_name == "slack.dm.list":
            result = await client.list_dm_conversations(
                limit=args.get("limit", 100),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.dm.group_list":
            result = await client.list_group_dms(
                limit=args.get("limit", 100),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.dm.send":
            result = await client.send_dm(
                user_id=args["user_id"],
                text=args["text"],
                thread_ts=args.get("thread_ts"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.dm.history":
            result = await client.get_dm_history(
                user_id=args["user_id"],
                limit=args.get("limit", 100),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.dm.open":
            result = await client.open_dm(args["user_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.dm.open_group":
            result = await client.open_group_dm(args["user_ids"])
            return ToolResult(success=True, data=result)

        # === USER LOOKUP ===
        elif tool_name == "slack.users.find_by_email":
            result = await client.get_user_by_email(args["email"])
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.users.info":
            result = await client.get_user_info(args["user_id"])
            return ToolResult(success=True, data=result)

        # === CANVAS ===
        elif tool_name == "slack.canvas.create":
            document_content = None
            if args.get("markdown"):
                document_content = {"type": "markdown", "markdown": args["markdown"]}
            result = await client.create_canvas(
                title=args["title"],
                document_content=document_content,
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.canvas.edit":
            operation = args.get("operation", "insert_at_end")
            changes = [{
                "operation": operation,
                "document_content": {
                    "type": "markdown",
                    "markdown": args["markdown"],
                },
            }]
            result = await client.edit_canvas(
                canvas_id=args["canvas_id"],
                changes=changes,
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.canvas.delete":
            result = await client.delete_canvas(args["canvas_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.canvas.share":
            result = await client.set_canvas_access(
                canvas_id=args["canvas_id"],
                access_level=args.get("access_level", "read"),
                channel_ids=args.get("channel_ids"),
                user_ids=args.get("user_ids"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.canvas.sections_lookup":
            result = await client.lookup_canvas_sections(
                canvas_id=args["canvas_id"],
                section_types=args.get("section_types"),
                contains_text=args.get("contains_text"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "slack.canvas.access_list":
            result = await client.list_canvas_access(args["canvas_id"])
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
