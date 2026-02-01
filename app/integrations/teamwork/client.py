from typing import Optional, Any
import httpx


class TeamworkClient:
    def __init__(self, access_token: str, site_url: str):
        self.access_token = access_token
        self.base_url = site_url.rstrip("/")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
    ) -> dict:
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=self._headers(),
                params=params,
                json=json_data,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def list_projects(self, page: int = 1, page_size: int = 50) -> dict:
        return await self._request(
            "GET",
            "/projects.json",
            params={"page": page, "pageSize": page_size},
        )

    async def list_people(self, page: int = 1, page_size: int = 50) -> dict:
        return await self._request(
            "GET",
            "/people.json",
            params={"page": page, "pageSize": page_size},
        )

    async def list_tasks(
        self,
        project_id: Optional[int] = None,
        assignee_id: Optional[int] = None,
        status: Optional[str] = None,
        due_after: Optional[str] = None,
        due_before: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "pageSize": page_size}

        if project_id:
            params["projectId"] = project_id
        if assignee_id:
            params["responsiblePartyId"] = assignee_id
        if status:
            params["filter"] = status
        if due_after:
            params["startDate"] = due_after
        if due_before:
            params["endDate"] = due_before

        return await self._request("GET", "/tasks.json", params=params)

    async def create_task(
        self,
        project_id: int,
        tasklist_id: int,
        content: str,
        description: Optional[str] = None,
        assignee_id: Optional[int] = None,
        due_date: Optional[str] = None,
    ) -> dict:
        task_data: dict[str, Any] = {"content": content}

        if description:
            task_data["description"] = description
        if assignee_id:
            task_data["responsible-party-id"] = str(assignee_id)
        if due_date:
            task_data["due-date"] = due_date

        return await self._request(
            "POST",
            f"/tasklists/{tasklist_id}/tasks.json",
            json_data={"todo-item": task_data},
        )

    async def update_task(self, task_id: int, **fields) -> dict:
        task_data = {}
        if "content" in fields:
            task_data["content"] = fields["content"]
        if "description" in fields:
            task_data["description"] = fields["description"]
        if "assignee_id" in fields:
            task_data["responsible-party-id"] = str(fields["assignee_id"])
        if "due_date" in fields:
            task_data["due-date"] = fields["due_date"]

        return await self._request(
            "PUT",
            f"/tasks/{task_id}.json",
            json_data={"todo-item": task_data},
        )

    async def complete_task(self, task_id: int) -> dict:
        return await self._request("PUT", f"/tasks/{task_id}/complete.json")

    async def get_tasklists(self, project_id: int) -> dict:
        return await self._request(
            "GET", f"/projects/{project_id}/tasklists.json"
        )
