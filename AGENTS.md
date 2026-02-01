# Repository Guidelines

## Project Structure & Module Organization
- `app/` is the FastAPI application source. Key modules: `app/main.py` (app entry + router wiring), `app/settings.py` (env-driven config), `app/db/` (SQLite connection + migrations), `app/auth/`, `app/integrations/`, `app/mcp_gateway/`, `app/admin/`, and `app/ui/` (templates + routes).
- `app/migrations/` contains ordered SQL files applied on startup.
- `docker/` includes `Dockerfile` and `docker-compose.yml` for local orchestration.
- `data/` is the default SQLite volume directory; the DB path is configured by `DATABASE_PATH` (defaults to `/data/app.db`).
- `requirements.txt` pins runtime dependencies.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` installs backend dependencies.
- `uvicorn app.main:app --host 0.0.0.0 --port 8000` runs the API locally.
- `python app/main.py` also starts the server (uses the same FastAPI app).
- `cd docker && docker-compose up -d` launches the app via Docker Compose.

## Coding Style & Naming Conventions
- Python code uses standard PEP 8 conventions (4-space indentation, snake_case for modules/functions, PascalCase for classes).
- Routes are grouped by feature folder (e.g., `app/auth/routes.py`, `app/integrations/routes.py`).
- No formatter or linter is configured in this repo; if you introduce one, document it here.

## Testing Guidelines
- No test suite is present in this checkout (no `tests/` directory or test runner config).
- If adding tests, prefer `pytest` and place files under `tests/` with names like `test_<feature>.py`.
- Document any required fixtures (e.g., a temp SQLite DB) alongside the tests.

## Commit & Pull Request Guidelines
- Git history is not available in this workspace, so commit conventions cannot be inferred. Use concise, imperative messages (e.g., “Add Slack OAuth refresh”) unless the repo owner specifies otherwise.
- PRs should include a clear description, affected endpoints/routes, and screenshots for UI changes (templates in `app/ui/templates/`).
- Link relevant issues and note any required environment variables or migration impacts.

## Security & Configuration Tips
- Copy `.env.example` to `.env` and replace all default secrets before running.
- Sensitive keys include `JWT_SECRET`, `TOKENS_ENCRYPTION_KEY`, and OAuth client secrets.
- Keep the database path in `DATABASE_PATH` writable for migrations on startup.
