from typing import Optional

from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.figma.client import FigmaClient


FIGMA_TOOLS = [
    # =====================================================
    # PRIMARY TOOL — use this for all coding/design tasks
    # =====================================================
    ToolDefinition(
        name="figma.dev.get_page",
        description=(
            "THE ONLY TOOL YOU NEED for coding HTML/CSS from Figma. Two modes:\n"
            "\n"
            "MODE 1 — OVERVIEW (without node_id): Call first to see file structure. "
            "Returns a map of all pages and frames with their node IDs, dimensions, and element counts. "
            "Pick the frames you want to code.\n"
            "\n"
            "MODE 2 — CSS OUTPUT (with node_id): Returns complete CSS-ready code: "
            "design tokens as CSS variables, image placeholders embedded (safe by default), "
            "and an HTML component tree with real CSS properties on every element "
            "(display, flex, gap, padding, background, font, color, border-radius, box-shadow, etc). "
            "Pass multiple node IDs comma-separated to batch them in ONE call.\n"
            "\n"
            "WORKFLOW: 1) Call without node_id → see frames and pick IDs. "
            "2) Call with node_id=\"1:2,3:4\" → get CSS + list of found images/icons. "
            "3) ONLY IF NEEDED: fetch images via figma.images.get_fills or figma.images.export. "
            "Image endpoints can trigger rate limits, so avoid unless necessary.\n"
            "\n"
            "NEVER use figma.files.get for coding — it returns raw JSON that can be millions of tokens."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key from Figma URL (the part after /file/ or /design/)"},
                "node_id": {
                    "type": "string",
                    "description": (
                        "Omit for overview mode (see file structure). "
                        "Set to frame/component node IDs for CSS output mode. "
                        "Comma-separated to batch multiple sections in one call: \"1:2,3:4,5:6\""
                    ),
                },
                "depth": {
                    "type": "integer",
                    "description": "Max tree depth. Overview default: 2. CSS mode default: unlimited.",
                },
                "resolve_images": {
                    "type": "boolean",
                    "description": (
                        "Fetch image URLs and export SVG icons (costs 2 extra API calls). "
                        "Default: false — images are NOT fetched (placeholders are embedded), saving API quota. "
                        "Set to true only when you need actual image URLs for implementation. "
                        "You can also fetch them separately: figma.images.get_fills and figma.images.export."
                    ),
                    "default": False,
                },
            },
            "required": ["file_key"],
        },
    ),
    # =====================================================
    # HELPER — use to discover page structure & node IDs
    # =====================================================
    ToolDefinition(
        name="figma.files.get_layout",
        description=(
            "Alternative to figma.dev.get_page overview mode. "
            "Returns a compact text tree with node types, names, IDs, dimensions, and layout info. "
            "Prefer figma.dev.get_page (without node_id) for the standard workflow — it gives a cleaner overview."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key from Figma URL"},
                "node_id": {"type": "string", "description": "Specific node ID to focus on. Comma-separated for multiple."},
                "depth": {"type": "integer", "description": "Max depth (use 1-2 for overview, higher for detail)"},
                "format": {
                    "type": "string",
                    "enum": ["json", "text"],
                    "description": "Output format: 'text' (default, readable tree) or 'json' (structured)",
                    "default": "text",
                },
            },
            "required": ["file_key"],
        },
    ),
    # =====================================================
    # UTILITY TOOLS
    # =====================================================
    ToolDefinition(
        name="figma.users.me",
        description="Get the current Figma user info (id, handle, email).",
        input_schema={"type": "object", "properties": {}},
    ),
    ToolDefinition(
        name="figma.files.get_meta",
        description="Get lightweight file metadata (name, last modified, version, thumbnail). Fast, no tree data.",
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
            },
            "required": ["file_key"],
        },
    ),
    # =====================================================
    # RAW API — avoid for coding tasks (huge output)
    # =====================================================
    ToolDefinition(
        name="figma.files.get",
        description=(
            "WARNING: Returns raw Figma JSON — can be MILLIONS of tokens on large files. "
            "Do NOT use for coding/design tasks. Use figma.dev.get_page instead. "
            "Only use this for inspecting raw API data or debugging. Always set depth=1 or depth=2."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key from Figma URL"},
                "depth": {"type": "integer", "description": "REQUIRED for safety. Depth of tree traversal (1=pages, 2=frames)"},
                "node_id": {"type": "string", "description": "Return only subtree from this node ID"},
            },
            "required": ["file_key"],
        },
    ),
    ToolDefinition(
        name="figma.files.get_nodes",
        description=(
            "WARNING: Returns raw Figma JSON for specific nodes — can be very large. "
            "For coding tasks, use figma.dev.get_page with node_id instead. "
            "Only use this for raw API inspection or debugging."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of node IDs",
                },
                "depth": {"type": "integer", "description": "Depth of tree traversal"},
            },
            "required": ["file_key", "ids"],
        },
    ),
    # === IMAGES ===
    ToolDefinition(
        name="figma.images.export",
        description=(
            "Export nodes as images (PNG, SVG, JPG, PDF). Batch multiple node IDs in one call. "
            "Use this after figma.dev.get_page to export specific icons/vectors as SVG. "
            "The ASSETS section of dev.get_page output lists vector node IDs you can pass here. "
            "Keep batch size under 20 to avoid rate limits."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file_key": {"type": "string", "description": "File key"},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Node IDs to export (batch them — one API call for all)",
                },
                "format": {
                    "type": "string",
                    "description": "Image format: svg for icons, png for photos/complex graphics",
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
        description=(
            "Get download URLs for all background images in a Figma file. "
            "Use after figma.dev.get_page to resolve image_ref values from the ASSETS section. "
            "One API call returns URLs for ALL image fills in the file."
        ),
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
        # === DEV (CSS-ready) ===
        if tool_name == "figma.dev.get_page":
            from app.integrations.figma.css_extractor import extract_page_css

            result_text = await extract_page_css(
                client=client,
                file_key=args["file_key"],
                node_id=args.get("node_id"),
                depth=args.get("depth"),
                resolve_images=args.get("resolve_images", False),
            )
            return ToolResult(success=True, data={"output": result_text})

        # === LAYOUT ===
        elif tool_name == "figma.files.get_layout":
            from app.integrations.figma.layout import transform_to_layout, layout_to_text

            node_id = args.get("node_id")
            depth = args.get("depth")
            output_format = args.get("format", "text")

            if node_id:
                ids = [n.strip() for n in node_id.split(",")]
                raw = await client.get_file_nodes(
                    file_key=args["file_key"],
                    ids=ids,
                    depth=depth or 10,
                )
            else:
                raw = await client.get_file(
                    file_key=args["file_key"],
                    depth=depth or 2,
                )

            layout = transform_to_layout(raw, max_depth=depth or 10)

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
