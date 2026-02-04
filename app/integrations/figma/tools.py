from typing import Optional

from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.figma.client import FigmaClient


FIGMA_TOOLS = [
    # === USER ===
    ToolDefinition(
        name="figma.users.me",
        description="Get the current authenticated Figma user (id, handle, email). Useful for identifying the user.",
        input_schema={"type": "object", "properties": {}},
    ),
    # === LAYOUT (compact) ===
    ToolDefinition(
        name="figma.files.get_layout",
        description=(
            "Get a compact, CSS-oriented layout tree from a Figma file. "
            "Returns only structure, dimensions, auto-layout, colors (hex), fonts, text content, "
            "border-radius, shadows — everything needed for HTML/CSS coding. "
            "Much smaller than raw file data (typically 2-5% of original size). "
            "Use this instead of figma.files.get when you need to code a design. "
            "Supports output as structured JSON or as a human-readable text tree. "
            "You can target specific nodes by ID to reduce output further."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key from Figma URL"},
                "node_id": {"type": "string", "description": "Specific node ID to extract (reduces output). Comma-separated for multiple."},
                "depth": {"type": "integer", "description": "Max depth of tree traversal (default: unlimited)"},
                "format": {
                    "type": "string",
                    "enum": ["json", "text"],
                    "description": "Output format: 'json' for structured data, 'text' for readable tree (default: text)",
                    "default": "text",
                },
            },
            "required": ["file_key"],
        },
    ),
    # === FILES (raw) ===
    ToolDefinition(
        name="figma.files.get",
        description="Get a Figma file by its file key. Returns the full document tree with pages, frames, and layers. Use depth to limit tree traversal. The file key is the string after /file/ or /design/ in a Figma URL.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key from Figma URL (e.g., 'abc123XYZ')"},
                "depth": {"type": "integer", "description": "Depth of tree traversal (1=pages only, 2=pages+frames, etc.)"},
                "node_id": {"type": "string", "description": "Return only the subtree starting from this node ID"},
            },
            "required": ["file_key"],
        },
    ),
    ToolDefinition(
        name="figma.files.get_nodes",
        description="Get specific nodes from a Figma file by their IDs. More efficient than fetching the entire file when you know which nodes you need.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of node IDs to retrieve (e.g., ['1:2', '3:4'])",
                },
                "depth": {"type": "integer", "description": "Depth of tree traversal for each node"},
            },
            "required": ["file_key", "ids"],
        },
    ),
    ToolDefinition(
        name="figma.files.get_meta",
        description="Get lightweight metadata for a Figma file (name, last modified date, version, thumbnail URL). Much faster than fetching the full file.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    # === IMAGES ===
    ToolDefinition(
        name="figma.images.export",
        description="Export rendered images from Figma file nodes. Returns temporary URLs for downloaded images. Supports PNG, SVG, JPG, and PDF formats.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node IDs to export as images (e.g., ['1:2', '3:4'])",
                },
                "format": {
                    "type": "string",
                    "description": "Image format",
                    "enum": ["png", "svg", "jpg", "pdf"],
                    "default": "png",
                },
                "scale": {"type": "number", "description": "Image scale (0.01 to 4.0)", "default": 1.0},
            },
            "required": ["file_key", "ids"],
        },
    ),
    ToolDefinition(
        name="figma.images.get_fills",
        description="Get download URLs for all images used as fills in a Figma file. Returns a mapping of image references to their URLs.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    # === VERSIONS ===
    ToolDefinition(
        name="figma.files.versions",
        description="Get the version history of a Figma file. Shows who made changes and when.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    # === COMMENTS ===
    ToolDefinition(
        name="figma.comments.list",
        description="List all comments on a Figma file, including replies and resolved status.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    ToolDefinition(
        name="figma.comments.create",
        description="Post a comment on a Figma file. Optionally attach to a specific node.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
                "message": {"type": "string", "description": "Comment text"},
                "node_id": {"type": "string", "description": "Node ID to attach the comment to (optional)"},
            },
            "required": ["file_key", "message"],
        },
    ),
    ToolDefinition(
        name="figma.comments.delete",
        description="Delete a comment from a Figma file.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
                "comment_id": {"type": "string", "description": "Comment ID to delete"},
            },
            "required": ["file_key", "comment_id"],
        },
    ),
    # === PROJECTS ===
    ToolDefinition(
        name="figma.projects.list",
        description="List all projects in a Figma team. Requires the team ID.",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Team ID"},
            },
            "required": ["team_id"],
        },
    ),
    ToolDefinition(
        name="figma.projects.files",
        description="List all files in a Figma project.",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "string", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
    # === COMPONENTS ===
    ToolDefinition(
        name="figma.components.list_team",
        description="List published components in a Figma team library. Supports pagination.",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Team ID"},
                "page_size": {"type": "integer", "description": "Number of items per page (max 30)"},
                "cursor": {"type": "string", "description": "Pagination cursor from previous response"},
            },
            "required": ["team_id"],
        },
    ),
    ToolDefinition(
        name="figma.components.list_file",
        description="List all components in a specific Figma file.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    ToolDefinition(
        name="figma.components.get",
        description="Get metadata for a specific component by its unique key.",
        input_schema={
            "type": "object",
            "properties": {
                "component_key": {"type": "string", "description": "Component key"},
            },
            "required": ["component_key"],
        },
    ),
    # === STYLES ===
    ToolDefinition(
        name="figma.styles.list_team",
        description="List published styles (colors, text styles, effects, grids) in a Figma team library. Supports pagination.",
        input_schema={
            "type": "object",
            "properties": {
                "team_id": {"type": "string", "description": "Team ID"},
                "page_size": {"type": "integer", "description": "Number of items per page (max 30)"},
                "cursor": {"type": "string", "description": "Pagination cursor from previous response"},
            },
            "required": ["team_id"],
        },
    ),
    ToolDefinition(
        name="figma.styles.list_file",
        description="List all styles defined in a specific Figma file.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    ToolDefinition(
        name="figma.styles.get",
        description="Get metadata for a specific style by its unique key.",
        input_schema={
            "type": "object",
            "properties": {
                "style_key": {"type": "string", "description": "Style key"},
            },
            "required": ["style_key"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    client = FigmaClient(access_token)

    try:
        # === LAYOUT ===
        if tool_name == "figma.files.get_layout":
            from app.integrations.figma.layout import transform_to_layout, layout_to_text

            node_id = args.get("node_id")
            depth = args.get("depth")
            output_format = args.get("format", "text")

            if node_id:
                ids = [n.strip() for n in node_id.split(",")]
                raw = await client.get_file_nodes(
                    file_key=args["file_key"],
                    ids=ids,
                    depth=depth,
                )
            else:
                raw = await client.get_file(
                    file_key=args["file_key"],
                    depth=depth,
                )

            layout = transform_to_layout(raw, max_depth=depth or 50)

            if output_format == "text":
                text = layout_to_text(layout)
                return ToolResult(success=True, data={"layout": text})
            return ToolResult(success=True, data=layout)

        # === USER ===
        elif tool_name == "figma.users.me":
            if meta and meta.get("user_id"):
                return ToolResult(
                    success=True,
                    data={
                        "user_id": meta.get("user_id"),
                        "handle": meta.get("handle"),
                        "email": meta.get("email"),
                        "img_url": meta.get("img_url"),
                        "raw_meta": meta,
                    },
                )
            result = await client.get_me()
            return ToolResult(success=True, data=result)

        # === FILES ===
        elif tool_name == "figma.files.get":
            result = await client.get_file(
                file_key=args["file_key"],
                depth=args.get("depth"),
                node_id=args.get("node_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.files.get_nodes":
            result = await client.get_file_nodes(
                file_key=args["file_key"],
                ids=args["ids"],
                depth=args.get("depth"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.files.get_meta":
            result = await client.get_file_meta(args["file_key"])
            return ToolResult(success=True, data=result)

        # === IMAGES ===
        elif tool_name == "figma.images.export":
            result = await client.get_images(
                file_key=args["file_key"],
                ids=args["ids"],
                format=args.get("format", "png"),
                scale=args.get("scale"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.images.get_fills":
            result = await client.get_image_fills(args["file_key"])
            return ToolResult(success=True, data=result)

        # === VERSIONS ===
        elif tool_name == "figma.files.versions":
            result = await client.get_file_versions(args["file_key"])
            return ToolResult(success=True, data=result)

        # === COMMENTS ===
        elif tool_name == "figma.comments.list":
            result = await client.get_comments(args["file_key"])
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.comments.create":
            result = await client.post_comment(
                file_key=args["file_key"],
                message=args["message"],
                node_id=args.get("node_id"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.comments.delete":
            result = await client.delete_comment(
                file_key=args["file_key"],
                comment_id=args["comment_id"],
            )
            return ToolResult(success=True, data=result)

        # === PROJECTS ===
        elif tool_name == "figma.projects.list":
            result = await client.get_team_projects(args["team_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.projects.files":
            result = await client.get_project_files(args["project_id"])
            return ToolResult(success=True, data=result)

        # === COMPONENTS ===
        elif tool_name == "figma.components.list_team":
            result = await client.get_team_components(
                team_id=args["team_id"],
                page_size=args.get("page_size"),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.components.list_file":
            result = await client.get_file_components(args["file_key"])
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.components.get":
            result = await client.get_component(args["component_key"])
            return ToolResult(success=True, data=result)

        # === STYLES ===
        elif tool_name == "figma.styles.list_team":
            result = await client.get_team_styles(
                team_id=args["team_id"],
                page_size=args.get("page_size"),
                cursor=args.get("cursor"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.styles.list_file":
            result = await client.get_file_styles(args["file_key"])
            return ToolResult(success=True, data=result)

        elif tool_name == "figma.styles.get":
            result = await client.get_style(args["style_key"])
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
