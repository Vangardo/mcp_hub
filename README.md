# MCP Hub

Multi-user MCP gateway that unifies Slack, Teamwork, and Telegram into a single server for GPT and other MCP clients. Users connect integrations once, then consume tools through one MCP endpoint with clear, per-integration configuration.

## Features

- Multi-user auth with admin approval flow and account management
- OAuth integrations (Slack, Teamwork) + Telegram MTProto (Telethon)
- MCP JSON-RPC gateway with per-provider routing and audit logging
- GPT config export (Bearer JSON + OAuth client credentials)
- Personal Access Tokens (PAT) for long-lived access
- Admin settings for public URL and integration credentials

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env
# edit .env
cd docker
docker-compose up -d
```

Open http://localhost:8000

### Local

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Configuration

### Environment Variables

Required:
- `ADMIN_EMAIL`, `ADMIN_PASSWORD`
- `JWT_SECRET`, `TOKENS_ENCRYPTION_KEY`
- `BASE_URL` (internal server URL, used for redirects if public URL is not set)

Optional:
- `DATABASE_PATH` (default: `data/app.db`)
- `TEAMWORK_CLIENT_ID`, `TEAMWORK_CLIENT_SECRET`
- `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`

### Admin Settings (UI)

In **Admin → Settings**, configure:
- Public Base URL / Public Host (used in GPT config + OAuth redirects)
- Slack/Teamwork OAuth credentials
- Telegram API ID / Hash

## Migrations & Database

SQLite is created at `DATABASE_PATH` (default `data/app.db`). The schema is initialized from a single migration:

- `app/migrations/001_init.sql`

Migrations run automatically on startup.

## Usage

### User Flow

1. Log in (or request access via Sign Up).
2. Connect integrations on **Integrations**.
3. Click **Get GPT Config** (global) or **Config** on a specific integration.
4. Choose **Bearer JSON** (PAT/JWT) or **OAuth** (ChatGPT-style).

### Admin Flow

- Approve/Reject users in **Admin → Users**.
- View audit logs and usage stats in **Admin → Audit**.
- Update public URL and integration credentials in **Admin → Settings**.

## GPT / MCP Client Setup

### Option A: Bearer JSON (PAT recommended)

Use the JSON from **Get GPT Config** with a PAT. This is the simplest path for MCP clients.

### Option B: OAuth Client Credentials (ChatGPT)

1. In **Get GPT Config → OAuth**, create or select client credentials.
2. Use `client_credentials` to obtain a token:

```bash
curl -X POST http://localhost:8000/oauth/token \
  -H 'Content-Type: application/json' \
  -d '{"grant_type":"client_credentials","client_id":"...","client_secret":"..."}'
```

3. Use the returned access token as `Authorization: Bearer <token>`.

## MCP Tools

Use `hub.integrations.list` to discover connected integrations and tools. Common tools:

- Teamwork: `teamwork.projects.list`, `teamwork.tasks.*`, `teamwork.people.list`
- Slack: `slack.channels.list`, `slack.messages.*`, `slack.users.list`
- Telegram: `telegram.dialogs.list`, `telegram.messages.send`, `telegram.messages.search`, `telegram.messages.history`

## API Docs

Open `/docs` for interactive API documentation and request/response examples.
