from typing import Optional
from app.integrations.base import ToolDefinition, ToolResult
from app.integrations.teamwork.client import TeamworkClient


TEAMWORK_TOOLS = [
    ToolDefinition(
        name="teamwork.projects.list",
        description="List all projects in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.people.list",
        description="List all people/users in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.list",
        description="List tasks in Teamwork with optional filters",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "assignee_id": {"type": "integer", "description": "Filter by assignee ID"},
                "status": {
                    "type": "string",
                    "description": "Filter by status",
                    "enum": ["all", "active", "completed", "late"],
                },
                "due_after": {"type": "string", "description": "Due date after (YYYYMMDD)"},
                "due_before": {"type": "string", "description": "Due date before (YYYYMMDD)"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.create",
        description="Create a new task in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
                "tasklist_id": {"type": "integer", "description": "Task list ID"},
                "content": {"type": "string", "description": "Task title/content"},
                "description": {"type": "string", "description": "Task description"},
                "assignee_id": {"type": "integer", "description": "Assignee user ID"},
                "due_date": {"type": "string", "description": "Due date (YYYYMMDD)"},
            },
            "required": ["project_id", "tasklist_id", "content"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.update",
        description="Update an existing task in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to update"},
                "content": {"type": "string", "description": "New task title"},
                "description": {"type": "string", "description": "New description"},
                "assignee_id": {"type": "integer", "description": "New assignee ID"},
                "due_date": {"type": "string", "description": "New due date (YYYYMMDD)"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.complete",
        description="Mark a task as complete in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID to complete"},
            },
            "required": ["task_id"],
        },
    ),
    ToolDefinition(
        name="teamwork.tasklists.list",
        description="List task lists for a project in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Project ID"},
            },
            "required": ["project_id"],
        },
    ),
]


async def execute_tool(
    tool_name: str,
    args: dict,
    access_token: str,
    meta: Optional[dict] = None,
) -> ToolResult:
    site_url = meta.get("site_url", "") if meta else ""
    if not site_url:
        return ToolResult(success=False, error="Site URL not configured")

    client = TeamworkClient(access_token, site_url)

    try:
        if tool_name == "teamwork.projects.list":
            result = await client.list_projects(
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.people.list":
            result = await client.list_people(
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.list":
            result = await client.list_tasks(
                project_id=args.get("project_id"),
                assignee_id=args.get("assignee_id"),
                status=args.get("status"),
                due_after=args.get("due_after"),
                due_before=args.get("due_before"),
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.create":
            result = await client.create_task(
                project_id=args["project_id"],
                tasklist_id=args["tasklist_id"],
                content=args["content"],
                description=args.get("description"),
                assignee_id=args.get("assignee_id"),
                due_date=args.get("due_date"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.update":
            update_fields = {
                k: v for k, v in args.items()
                if k != "task_id" and v is not None
            }
            result = await client.update_task(args["task_id"], **update_fields)
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.complete":
            result = await client.complete_task(args["task_id"])
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasklists.list":
            result = await client.get_tasklists(args["project_id"])
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
