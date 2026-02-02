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
                "priority": {
                    "type": "string",
                    "description": "Task priority",
                    "enum": ["none", "low", "medium", "high"],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Array of tag IDs to assign",
                },
                "estimated_minutes": {
                    "type": "integer",
                    "description": "Estimated time in minutes",
                },
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
                "priority": {
                    "type": "string",
                    "description": "Task priority",
                    "enum": ["none", "low", "medium", "high"],
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Array of tag IDs to assign",
                },
                "estimated_minutes": {
                    "type": "integer",
                    "description": "Estimated time in minutes",
                },
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
    ToolDefinition(
        name="teamwork.tags.list",
        description="List all available tags in Teamwork",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Optional: filter by project ID"},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.tasks.get",
        description="Get details of a single task by ID",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    ),
    # === SUBTASKS ===
    ToolDefinition(
        name="teamwork.subtasks.create",
        description="Create a subtask under a parent task",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "integer", "description": "Parent task ID"},
                "content": {"type": "string", "description": "Subtask title"},
                "description": {"type": "string", "description": "Subtask description"},
                "assignee_id": {"type": "integer", "description": "Assignee user ID"},
                "due_date": {"type": "string", "description": "Due date (YYYYMMDD)"},
                "estimated_minutes": {"type": "integer", "description": "Estimated time in minutes"},
            },
            "required": ["parent_task_id", "content"],
        },
    ),
    ToolDefinition(
        name="teamwork.subtasks.list",
        description="List subtasks of a parent task",
        input_schema={
            "type": "object",
            "properties": {
                "parent_task_id": {"type": "integer", "description": "Parent task ID"},
            },
            "required": ["parent_task_id"],
        },
    ),
    # === TIME ENTRIES ===
    ToolDefinition(
        name="teamwork.time.log",
        description="Log time entry for a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "hours": {"type": "integer", "description": "Hours spent"},
                "minutes": {"type": "integer", "description": "Minutes spent"},
                "date": {"type": "string", "description": "Date (YYYYMMDD)"},
                "description": {"type": "string", "description": "Description of work done"},
                "user_id": {"type": "integer", "description": "User ID (default: current user)"},
                "is_billable": {"type": "boolean", "description": "Is billable time", "default": False},
            },
            "required": ["task_id", "hours", "minutes", "date"],
        },
    ),
    ToolDefinition(
        name="teamwork.time.list",
        description="List time entries with optional filters",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Filter by task ID"},
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "user_id": {"type": "integer", "description": "Filter by user ID"},
                "from_date": {"type": "string", "description": "Start date (YYYYMMDD)"},
                "to_date": {"type": "string", "description": "End date (YYYYMMDD)"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
        },
    ),
    ToolDefinition(
        name="teamwork.time.totals",
        description="Get time totals summary (useful for daily/weekly reports)",
        input_schema={
            "type": "object",
            "properties": {
                "project_id": {"type": "integer", "description": "Filter by project ID"},
                "user_id": {"type": "integer", "description": "Filter by user ID"},
                "from_date": {"type": "string", "description": "Start date (YYYYMMDD)"},
                "to_date": {"type": "string", "description": "End date (YYYYMMDD)"},
            },
        },
    ),
    # === COMMENTS ===
    ToolDefinition(
        name="teamwork.comments.add",
        description="Add a comment to a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "body": {"type": "string", "description": "Comment text"},
                "notify": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "User IDs to notify",
                },
            },
            "required": ["task_id", "body"],
        },
    ),
    ToolDefinition(
        name="teamwork.comments.list",
        description="List comments for a task",
        input_schema={
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "Task ID"},
                "page": {"type": "integer", "description": "Page number", "default": 1},
                "page_size": {"type": "integer", "description": "Items per page", "default": 50},
            },
            "required": ["task_id"],
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
                priority=args.get("priority"),
                tags=args.get("tags"),
                estimated_minutes=args.get("estimated_minutes"),
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

        elif tool_name == "teamwork.tags.list":
            result = await client.list_tags(project_id=args.get("project_id"))
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.tasks.get":
            result = await client.get_task(args["task_id"])
            return ToolResult(success=True, data=result)

        # === SUBTASKS ===
        elif tool_name == "teamwork.subtasks.create":
            result = await client.create_subtask(
                parent_task_id=args["parent_task_id"],
                content=args["content"],
                description=args.get("description"),
                assignee_id=args.get("assignee_id"),
                due_date=args.get("due_date"),
                estimated_minutes=args.get("estimated_minutes"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.subtasks.list":
            result = await client.list_subtasks(args["parent_task_id"])
            return ToolResult(success=True, data=result)

        # === TIME ENTRIES ===
        elif tool_name == "teamwork.time.log":
            result = await client.log_time(
                task_id=args["task_id"],
                hours=args["hours"],
                minutes=args["minutes"],
                date=args["date"],
                description=args.get("description"),
                user_id=args.get("user_id"),
                is_billable=args.get("is_billable", False),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.time.list":
            result = await client.list_time_entries(
                task_id=args.get("task_id"),
                project_id=args.get("project_id"),
                user_id=args.get("user_id"),
                from_date=args.get("from_date"),
                to_date=args.get("to_date"),
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.time.totals":
            result = await client.get_time_totals(
                project_id=args.get("project_id"),
                user_id=args.get("user_id"),
                from_date=args.get("from_date"),
                to_date=args.get("to_date"),
            )
            return ToolResult(success=True, data=result)

        # === COMMENTS ===
        elif tool_name == "teamwork.comments.add":
            result = await client.add_comment(
                task_id=args["task_id"],
                body=args["body"],
                notify=args.get("notify"),
            )
            return ToolResult(success=True, data=result)

        elif tool_name == "teamwork.comments.list":
            result = await client.list_comments(
                task_id=args["task_id"],
                page=args.get("page", 1),
                page_size=args.get("page_size", 50),
            )
            return ToolResult(success=True, data=result)

        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

    except Exception as e:
        return ToolResult(success=False, error=str(e))
