from typing import Optional

from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.miro.client import MiroClient


MIRO_TOOLS = [
    # === BOARDS ===
    ToolDefinition(
        name="miro.boards.list",
        description="List or search Miro boards accessible to the user. Use query to search by board title. Returns board IDs needed for all other operations.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search boards by title"},
                "team_id": {"type": "string", "description": "Filter by team ID"},
                "limit": {"type": "integer", "description": "Max boards to return", "default": 20},
                "cursor": {"type": "string", "description": "Pagination cursor from previous response"},
            },
        },
    ),
    ToolDefinition(
        name="miro.boards.get",
        description="Get full details of a Miro board by ID, including name, description, owner, creation date, and sharing settings.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID (from boards.list)"},
            },
            "required": ["board_id"],
        },
    ),
    ToolDefinition(
        name="miro.boards.create",
        description="Create a new Miro board. Optionally assign to a specific team.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Board name"},
                "description": {"type": "string", "description": "Board description"},
                "team_id": {"type": "string", "description": "Team ID to create the board in"},
            },
            "required": ["name"],
        },
    ),
    ToolDefinition(
        name="miro.boards.update",
        description="Update a Miro board's name or description.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "name": {"type": "string", "description": "New board name"},
                "description": {"type": "string", "description": "New board description"},
            },
            "required": ["board_id"],
        },
    ),
    ToolDefinition(
        name="miro.boards.delete",
        description="Permanently delete a Miro board. This action cannot be undone.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID to delete"},
            },
            "required": ["board_id"],
        },
    ),
    ToolDefinition(
        name="miro.boards.copy",
        description="Create a copy of an existing Miro board with all its content.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID to copy"},
                "title": {"type": "string", "description": "Title for the new copy"},
            },
            "required": ["board_id"],
        },
    ),
    ToolDefinition(
        name="miro.boards.members",
        description="List all members of a Miro board and their roles (viewer, commenter, editor, owner).",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
            },
            "required": ["board_id"],
        },
    ),
    ToolDefinition(
        name="miro.users.me",
        description="Get the current authenticated Miro user (id, name). Useful for 'my boards' or 'assign to me'.",
        input_schema={"type": "object", "properties": {}},
    ),
    ToolDefinition(
        name="miro.boards.share",
        description="Share a Miro board with users by email. Set role to control their access level.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "emails": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Email addresses of users to invite",
                },
                "role": {
                    "type": "string",
                    "description": "Access role for invited users",
                    "enum": ["viewer", "commenter", "editor"],
                    "default": "commenter",
                },
            },
            "required": ["board_id", "emails"],
        },
    ),
    # === ITEMS (generic) ===
    ToolDefinition(
        name="miro.items.list",
        description="List all items on a Miro board. Filter by type to get only specific items. Supported types: sticky_note, text, shape, card, frame, image, document, embed, connector.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID (from boards.list)"},
                "type": {
                    "type": "string",
                    "description": "Filter by item type",
                    "enum": ["sticky_note", "text", "shape", "card", "frame", "image", "document", "embed", "connector"],
                },
                "limit": {"type": "integer", "description": "Max items to return", "default": 50},
                "cursor": {"type": "string", "description": "Pagination cursor"},
            },
            "required": ["board_id"],
        },
    ),
    ToolDefinition(
        name="miro.items.get",
        description="Get full details of a specific item on a Miro board, including content, position, style, and metadata.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "item_id": {"type": "string", "description": "Item ID (from items.list)"},
            },
            "required": ["board_id", "item_id"],
        },
    ),
    ToolDefinition(
        name="miro.items.delete",
        description="Delete any item from a Miro board by its ID.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "item_id": {"type": "string", "description": "Item ID to delete"},
            },
            "required": ["board_id", "item_id"],
        },
    ),
    # === STICKY NOTES ===
    ToolDefinition(
        name="miro.sticky_notes.bulk_create",
        description="Create up to 10 sticky notes on a Miro board (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Default board ID for items"},
                "items": {
                    "type": "array",
                    "description": "Sticky notes to create (max 10)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "Board ID"},
                            "content": {"type": "string", "description": "Sticky note text content"},
                            "color": {"type": "string", "description": "Fill color hex (#RRGGBB)"},
                            "position_x": {"type": "number", "description": "X position"},
                            "position_y": {"type": "number", "description": "Y position"},
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["items"],
        },
    ),
    ToolDefinition(
        name="miro.sticky_notes.update",
        description="Update the content or color of an existing sticky note.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "item_id": {"type": "string", "description": "Sticky note item ID"},
                "content": {"type": "string", "description": "New text content"},
                "color": {"type": "string", "description": "New fill color hex (#RRGGBB)"},
            },
            "required": ["board_id", "item_id"],
        },
    ),
    # === TEXT ===
    ToolDefinition(
        name="miro.text.bulk_create",
        description="Create up to 10 text items on a Miro board (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Default board ID for items"},
                "items": {
                    "type": "array",
                    "description": "Text items to create (max 10)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "Board ID"},
                            "content": {"type": "string", "description": "Text content"},
                            "position_x": {"type": "number", "description": "X position"},
                            "position_y": {"type": "number", "description": "Y position"},
                            "font_size": {"type": "integer", "description": "Font size in pixels"},
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["items"],
        },
    ),
    # === SHAPES ===
    ToolDefinition(
        name="miro.shapes.bulk_create",
        description="Create up to 10 shapes on a Miro board (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Default board ID for items"},
                "items": {
                    "type": "array",
                    "description": "Shapes to create (max 10)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "Board ID"},
                            "content": {"type": "string", "description": "Text inside the shape"},
                            "shape": {
                                "type": "string",
                                "description": "Shape type",
                                "enum": ["rectangle", "circle", "triangle", "rhombus", "round_rectangle",
                                         "parallelogram", "trapezoid", "pentagon", "hexagon", "octagon",
                                         "wedge_round_rectangle_callout", "star", "flow_chart_predefined_process",
                                         "right_arrow", "left_arrow", "left_right_arrow", "cloud", "cross",
                                         "can"],
                                "default": "rectangle",
                            },
                            "color": {"type": "string", "description": "Fill color hex (#RRGGBB)"},
                            "position_x": {"type": "number", "description": "X position"},
                            "position_y": {"type": "number", "description": "Y position"},
                            "width": {"type": "number", "description": "Shape width in pixels"},
                            "height": {"type": "number", "description": "Shape height in pixels"},
                        },
                    },
                },
            },
            "required": ["items"],
        },
    ),
    # === CARDS ===
    ToolDefinition(
        name="miro.cards.bulk_create",
        description="Create up to 10 cards on a Miro board (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Default board ID for items"},
                "items": {
                    "type": "array",
                    "description": "Cards to create (max 10)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "Board ID"},
                            "title": {"type": "string", "description": "Card title"},
                            "description": {"type": "string", "description": "Card description (supports HTML)"},
                            "position_x": {"type": "number", "description": "X position"},
                            "position_y": {"type": "number", "description": "Y position"},
                        },
                        "required": ["title"],
                    },
                },
            },
            "required": ["items"],
        },
    ),
    # === CONNECTORS ===
    ToolDefinition(
        name="miro.connectors.bulk_create",
        description="Create up to 10 connectors on a Miro board (processed sequentially)",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Default board ID for items"},
                "items": {
                    "type": "array",
                    "description": "Connectors to create (max 10)",
                    "items": {
                        "type": "object",
                        "properties": {
                            "board_id": {"type": "string", "description": "Board ID"},
                            "start_item_id": {"type": "string", "description": "Item ID where connector starts"},
                            "end_item_id": {"type": "string", "description": "Item ID where connector ends"},
                            "style": {
                                "type": "string",
                                "description": "Line style",
                                "enum": ["normal", "dashed", "dotted"],
                            },
                        },
                        "required": ["start_item_id", "end_item_id"],
                    },
                },
            },
            "required": ["items"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    client = MiroClient(access_token)

    try:
        # === BOARDS ===
        if tool_name == "miro.boards.list":
            result = await client.list_boards(
                query=args.get("query"),
                team_id=args.get("team_id"),
                limit=args.get("limit", 20),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.get":
            result = await client.get_board(args["board_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.create":
            result = await client.create_board(
                name=args["name"],
                description=args.get("description"),
                team_id=args.get("team_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.update":
            result = await client.update_board(
                board_id=args["board_id"],
                name=args.get("name"),
                description=args.get("description"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.delete":
            result = await client.delete_board(args["board_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.copy":
            result = await client.copy_board(
                board_id=args["board_id"],
                title=args.get("title"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.members":
            result = await client.list_board_members(args["board_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.users.me":
            if meta and meta.get("user_id"):
                return ToolResult(
                    success=True,
                    data={
                        "user_id": meta.get("user_id"),
                        "user_name": meta.get("user_name"),
                        "team_id": meta.get("team_id"),
                        "team_name": meta.get("team_name"),
                        "raw_meta": meta,
                    },
                )
            result = await client.get_current_user()
            if isinstance(result, dict):
                team = result.get("team", {}) if isinstance(result.get("team"), dict) else {}
                user = result.get("user", {}) if isinstance(result.get("user"), dict) else {}
                return ToolResult(
                    success=True,
                    data={
                        "user_id": user.get("id"),
                        "user_name": user.get("name"),
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "raw": result,
                    },
                )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.boards.share":
            result = await client.share_board(
                board_id=args["board_id"],
                emails=args["emails"],
                role=args.get("role", "commenter"),
            )
            return ToolResult(success=True, data=result)

        # === ITEMS ===
        elif tool_name == "miro.items.list":
            result = await client.list_items(
                board_id=args["board_id"],
                item_type=args.get("type"),
                limit=args.get("limit", 50),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.items.get":
            result = await client.get_item(args["board_id"], args["item_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.items.delete":
            result = await client.delete_item(args["board_id"], args["item_id"])
            return ToolResult(success=True, data=result)

        # === STICKY NOTES ===
        elif tool_name == "miro.sticky_notes.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")
            default_board_id = args.get("board_id")
            results = []
            for idx, item in enumerate(items):
                try:
                    board_id = item.get("board_id") or default_board_id
                    if not board_id or not item.get("content"):
                        raise ValueError("board_id and content are required")
                    result = await client.create_sticky_note(
                        board_id=board_id,
                        content=item["content"],
                        color=item.get("color"),
                        position_x=item.get("position_x"),
                        position_y=item.get("position_y"),
                    )
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})
            return ToolResult(success=True, data={"count": len(results), "results": results})

        elif tool_name == "miro.sticky_notes.update":
            result = await client.update_sticky_note(
                board_id=args["board_id"],
                item_id=args["item_id"],
                content=args.get("content"),
                color=args.get("color"),
            )
            return ToolResult(success=True, data=result)

        # === TEXT ===
        elif tool_name == "miro.text.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")
            default_board_id = args.get("board_id")
            results = []
            for idx, item in enumerate(items):
                try:
                    board_id = item.get("board_id") or default_board_id
                    if not board_id or not item.get("content"):
                        raise ValueError("board_id and content are required")
                    result = await client.create_text(
                        board_id=board_id,
                        content=item["content"],
                        position_x=item.get("position_x"),
                        position_y=item.get("position_y"),
                        font_size=item.get("font_size"),
                    )
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})
            return ToolResult(success=True, data={"count": len(results), "results": results})

        # === SHAPES ===
        elif tool_name == "miro.shapes.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")
            default_board_id = args.get("board_id")
            results = []
            for idx, item in enumerate(items):
                try:
                    board_id = item.get("board_id") or default_board_id
                    if not board_id:
                        raise ValueError("board_id is required")
                    result = await client.create_shape(
                        board_id=board_id,
                        content=item.get("content"),
                        shape=item.get("shape", "rectangle"),
                        color=item.get("color"),
                        position_x=item.get("position_x"),
                        position_y=item.get("position_y"),
                        width=item.get("width"),
                        height=item.get("height"),
                    )
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})
            return ToolResult(success=True, data={"count": len(results), "results": results})

        # === CARDS ===
        elif tool_name == "miro.cards.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")
            default_board_id = args.get("board_id")
            results = []
            for idx, item in enumerate(items):
                try:
                    board_id = item.get("board_id") or default_board_id
                    if not board_id or not item.get("title"):
                        raise ValueError("board_id and title are required")
                    result = await client.create_card(
                        board_id=board_id,
                        title=item["title"],
                        description=item.get("description"),
                        position_x=item.get("position_x"),
                        position_y=item.get("position_y"),
                    )
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})
            return ToolResult(success=True, data={"count": len(results), "results": results})

        # === CONNECTORS ===
        elif tool_name == "miro.connectors.bulk_create":
            items = args.get("items") or []
            if len(items) > 10:
                return ToolResult(success=False, error="Max 10 items allowed for bulk_create")
            default_board_id = args.get("board_id")
            results = []
            for idx, item in enumerate(items):
                try:
                    board_id = item.get("board_id") or default_board_id
                    if not board_id or not item.get("start_item_id") or not item.get("end_item_id"):
                        raise ValueError("board_id, start_item_id and end_item_id are required")
                    result = await client.create_connector(
                        board_id=board_id,
                        start_item_id=item["start_item_id"],
                        end_item_id=item["end_item_id"],
                        style=item.get("style"),
                    )
                    results.append({"index": idx, "success": True, "data": result})
                except Exception as exc:
                    results.append({"index": idx, "success": False, "error": str(exc)})
            return ToolResult(success=True, data={"count": len(results), "results": results})

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
