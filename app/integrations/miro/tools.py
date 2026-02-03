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
        name="miro.sticky_notes.create",
        description="Create a sticky note on a Miro board. Specify content text and optional color and position.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "content": {"type": "string", "description": "Sticky note text content (supports basic HTML: <b>, <i>, <a>)"},
                "color": {
                    "type": "string",
                    "description": "Fill color hex (#RRGGBB) e.g. #FEF445 for yellow, #D5F692 for green",
                },
                "position_x": {"type": "number", "description": "X position on the board (center)"},
                "position_y": {"type": "number", "description": "Y position on the board (center)"},
            },
            "required": ["board_id", "content"],
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
        name="miro.text.create",
        description="Create a text item on a Miro board. For free-form text labels and annotations.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "content": {"type": "string", "description": "Text content (supports basic HTML)"},
                "position_x": {"type": "number", "description": "X position on the board"},
                "position_y": {"type": "number", "description": "Y position on the board"},
                "font_size": {"type": "integer", "description": "Font size in pixels"},
            },
            "required": ["board_id", "content"],
        },
    ),
    # === SHAPES ===
    ToolDefinition(
        name="miro.shapes.create",
        description="Create a shape on a Miro board. Useful for diagrams, flowcharts, and visual layouts.",
        input_schema={
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
            "required": ["board_id"],
        },
    ),
    # === CARDS ===
    ToolDefinition(
        name="miro.cards.create",
        description="Create a card on a Miro board. Cards are like mini documents with a title and description, useful for task tracking and Kanban boards.",
        input_schema={
            "type": "object",
            "properties": {
                "board_id": {"type": "string", "description": "Board ID"},
                "title": {"type": "string", "description": "Card title"},
                "description": {"type": "string", "description": "Card description (supports HTML)"},
                "position_x": {"type": "number", "description": "X position"},
                "position_y": {"type": "number", "description": "Y position"},
            },
            "required": ["board_id", "title"],
        },
    ),
    # === CONNECTORS ===
    ToolDefinition(
        name="miro.connectors.create",
        description="Create a connector (arrow/line) between two items on a Miro board. Use items.list to get item IDs.",
        input_schema={
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
            "required": ["board_id", "start_item_id", "end_item_id"],
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
        elif tool_name == "miro.sticky_notes.create":
            result = await client.create_sticky_note(
                board_id=args["board_id"],
                content=args["content"],
                color=args.get("color"),
                position_x=args.get("position_x"),
                position_y=args.get("position_y"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "miro.sticky_notes.update":
            result = await client.update_sticky_note(
                board_id=args["board_id"],
                item_id=args["item_id"],
                content=args.get("content"),
                color=args.get("color"),
            )
            return ToolResult(success=True, data=result)

        # === TEXT ===
        elif tool_name == "miro.text.create":
            result = await client.create_text(
                board_id=args["board_id"],
                content=args["content"],
                position_x=args.get("position_x"),
                position_y=args.get("position_y"),
                font_size=args.get("font_size"),
            )
            return ToolResult(success=True, data=result)

        # === SHAPES ===
        elif tool_name == "miro.shapes.create":
            result = await client.create_shape(
                board_id=args["board_id"],
                content=args.get("content"),
                shape=args.get("shape", "rectangle"),
                color=args.get("color"),
                position_x=args.get("position_x"),
                position_y=args.get("position_y"),
                width=args.get("width"),
                height=args.get("height"),
            )
            return ToolResult(success=True, data=result)

        # === CARDS ===
        elif tool_name == "miro.cards.create":
            result = await client.create_card(
                board_id=args["board_id"],
                title=args["title"],
                description=args.get("description"),
                position_x=args.get("position_x"),
                position_y=args.get("position_y"),
            )
            return ToolResult(success=True, data=result)

        # === CONNECTORS ===
        elif tool_name == "miro.connectors.create":
            result = await client.create_connector(
                board_id=args["board_id"],
                start_item_id=args["start_item_id"],
                end_item_id=args["end_item_id"],
                style=args.get("style"),
            )
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
