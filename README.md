# MCP Hub

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-0db7ed.svg)](docker/)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)

**MCP Hub** is a self-hosted, multi-user gateway that connects your favorite tools — **Teamwork**, **Slack**, **Telegram**, **Miro**, **Figma** — to AI assistants like **ChatGPT**, **Claude Desktop**, and **Cursor** via the Model Context Protocol (MCP).

One server. Multiple integrations. Full control over your data.

---

## Why MCP Hub?

| Problem | MCP Hub Solution |
|---------|------------------|
| ChatGPT can't access your Teamwork tasks | Connect once, use everywhere |
| Claude Desktop needs separate configs per tool | Single MCP endpoint for all integrations |
| Worried about token security | Tokens encrypted at rest, never exposed to AI |
| Need audit trail for compliance | Every AI action logged with user, tool, and result |
| Team needs shared access | Multi-user with admin approval workflow |
| Complex deployment | Single Docker container, SQLite, zero external deps |

---

## Key Features

### One Gateway, Many Integrations
- **Teamwork**: Projects, tasks, task lists, subtasks, time tracking, tags, comments, workflows
- **Slack**: Channels, messages, DMs, users, search, canvases
- **Telegram**: Dialogs, messages, search, history (via MTProto/Telethon)
- **Miro**: Boards, items, sticky notes, text, shapes, cards, connectors
- **Figma**: Dev layout extraction, images, comments, components, styles
- More integrations coming soon!

### Native MCP Protocol
- Works with **ChatGPT** (via OAuth 2.0 + PKCE)
- Works with **Claude Desktop** (via Bearer token)
- Works with **Cursor** and any MCP-compatible client
- JSON-RPC 2.0 over HTTP with streamable responses

### Enterprise-Ready Security
- **OAuth 2.0 + PKCE** for ChatGPT integration (RFC 8414, RFC 7591, RFC 9728)
- **AES-256 encryption** for stored tokens
- **JWT-based authentication** with configurable expiration
- **Personal Access Tokens (PAT)** for long-lived API access
- **Client Credentials** for machine-to-machine auth

### Full Audit Trail
- Every tool call logged with timestamp, user, provider, action, and status
- Request/response details for debugging
- Filter by user, provider, date range
- Export-ready for compliance

### Multi-User Support
- User registration with admin approval workflow
- Per-user integration connections (each user connects their own accounts)
- Role-based access (admin/user)
- User management dashboard

### Easy Deployment
- **Single Docker container** — `docker-compose up -d`
- **SQLite database** — no external database required
- **Zero external dependencies** — runs anywhere
- **Environment-based configuration** — 12-factor app ready

---

## Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/Vangardo/mcp_hub.git
cd mcp_hub

# Configure environment
cp .env.example .env
nano .env  # Edit with your settings

# Start with Docker Compose
cd docker
docker-compose up -d

# Access the UI
open http://localhost:8000
```

### Option 2: Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env

# Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Configuration

### Required Environment Variables

```bash
# Admin credentials (first user, auto-created)
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=your-secure-password

# Security keys (generate unique values!)
JWT_SECRET=your-jwt-secret-min-32-chars
TOKENS_ENCRYPTION_KEY=your-32-char-encryption-key

# Base URL (internal, used if public URL not set)
BASE_URL=http://localhost:8000
```

### Optional Environment Variables

```bash
# Database location
DATABASE_PATH=data/app.db

# Teamwork OAuth (get from https://developer.teamwork.com/)
TEAMWORK_CLIENT_ID=your-client-id
TEAMWORK_CLIENT_SECRET=your-client-secret

# Slack OAuth (get from https://api.slack.com/apps)
SLACK_CLIENT_ID=your-client-id
SLACK_CLIENT_SECRET=your-client-secret

# Miro OAuth (get from https://miro.com/app/settings/user-profile/apps)
MIRO_CLIENT_ID=your-client-id
MIRO_CLIENT_SECRET=your-client-secret

# Figma OAuth (get from https://www.figma.com/developers/apps)
FIGMA_CLIENT_ID=your-client-id
FIGMA_CLIENT_SECRET=your-client-secret

# Telegram MTProto (get from https://my.telegram.org/)
TELEGRAM_API_ID=your-api-id
TELEGRAM_API_HASH=your-api-hash
```

### Admin Settings (Web UI)

Navigate to **Admin → Settings** to configure:
- **Public Base URL** — Used for OAuth redirects and GPT config
- **Public Host** — Domain name for URL generation
- **Integration credentials** — Can also be set via environment

---

## Usage Guide

### For Users

1. **Sign Up** — Request access at `/signup`
2. **Wait for Approval** — Admin approves your request
3. **Connect Integrations** — On the Integrations page, connect Teamwork/Slack/Telegram/Miro/Figma
4. **Get Config** — Click "Get GPT Config" to get your MCP configuration
5. **Use with AI** — Paste config into ChatGPT, Claude, or Cursor

### For Admins

1. **Approve Users** — Navigate to Admin → Users
2. **Monitor Usage** — Check Admin → Audit for activity logs
3. **Configure Settings** — Set public URL and credentials in Admin → Settings
4. **Manage Integrations** — View all user connections

---

## Connecting to AI Assistants

### ChatGPT (Actions / GPT Builder)

1. In MCP Hub, click **Get GPT Config**
2. Switch to **OAuth** tab
3. Copy the **Server URL** (e.g., `https://your-domain.com/mcp`)
4. In ChatGPT, create a new Action with:
   - **Server URL**: Your MCP endpoint
   - **Authentication**: OAuth 2.0
   - ChatGPT will auto-discover OAuth endpoints via RFC 8414

### Claude Desktop

1. In MCP Hub, click **Get GPT Config**
2. Stay on **Bearer JSON** tab
3. Generate a **Personal Access Token (PAT)** for long-lived access
4. Copy the JSON config to your Claude Desktop settings

Example `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "mcp-hub": {
      "url": "https://your-domain.com/mcp",
      "headers": {
        "Authorization": "Bearer your-pat-token"
      }
    }
  }
}
```

### Cursor / Other MCP Clients

Same as Claude Desktop — use Bearer token authentication with the MCP endpoint URL.

---

## Available Tools

### Hub Tools
| Tool | Description |
|------|-------------|
| `hub.integrations.list` | List all connected integrations and available tools |
| `hub.tools.list` | List tools for a specific provider |
| `hub.tools.call` | Call a provider tool via the hub |

### Teamwork Tools
| Tool | Description |
|------|-------------|
| `teamwork.projects.list` | List all projects |
| `teamwork.people.list` | List team members |
| `teamwork.people.me` | Get current user |
| `teamwork.tasks.list` | List tasks with filters |
| `teamwork.tasks.due_today` | Get tasks due today |
| `teamwork.tasks.overdue` | Get overdue tasks |
| `teamwork.tasks.bulk_create` | Create up to 10 tasks |
| `teamwork.tasks.bulk_update` | Update up to 10 tasks |
| `teamwork.tasks.complete` | Mark task as complete |
| `teamwork.tasks.get` | Get a task by ID |
| `teamwork.tasklists.list` | List task lists in a project |
| `teamwork.subtasks.create` | Create a subtask |
| `teamwork.subtasks.list` | List subtasks |
| `teamwork.time.log` | Log time entry |
| `teamwork.time.list` | List time entries |
| `teamwork.time.totals` | Get time totals |
| `teamwork.tags.list` | List tags |
| `teamwork.tags.ensure` | Ensure tags exist |
| `teamwork.tags.create` | Create tag |
| `teamwork.tags.update` | Update tag |
| `teamwork.tags.delete` | Delete tag |
| `teamwork.comments.add` | Add comment to task |
| `teamwork.comments.list` | List task comments |
| `teamwork.workflows.list` | List workflow stages |
| `teamwork.stages.list` | List board columns |
| `teamwork.columns.list` | List board columns (alias) |
| `teamwork.tasks.set_stage` | Move task to stage |
| `teamwork.tasks.set_stage_by_name` | Move task by stage name |
| `teamwork.tasks.move_to_column` | Move task to column |
| `teamwork.tasks.move_to_column_by_name` | Move task by column name |

### Slack Tools
| Tool | Description |
|------|-------------|
| `slack.channels.list` | List all channels |
| `slack.users.list` | List workspace users |
| `slack.users.me` | Get current user |
| `slack.users.info` | Get user details |
| `slack.users.find_by_email` | Find user by email |
| `slack.messages.post` | Post message to channel |
| `slack.messages.history` | Get channel history |
| `slack.dm.list` | List direct messages |
| `slack.dm.group_list` | List group DMs |
| `slack.dm.send` | Send direct message |
| `slack.dm.history` | Get DM history |
| `slack.dm.open` | Open DM |
| `slack.dm.open_group` | Open group DM |
| `slack.canvas.create` | Create a canvas |
| `slack.canvas.edit` | Edit canvas content |
| `slack.canvas.delete` | Delete canvas |
| `slack.canvas.share` | Share canvas |
| `slack.canvas.sections_lookup` | Lookup canvas sections |
| `slack.canvas.access_list` | List canvas access |

### Telegram Tools
| Tool | Description |
|------|-------------|
| `telegram.users.me` | Get current user |
| `telegram.dialogs.list` | List all chats |
| `telegram.messages.send` | Send message |
| `telegram.messages.search` | Search messages |
| `telegram.messages.history` | Get chat history |

### Miro Tools
| Tool | Description |
|------|-------------|
| `miro.boards.list` | List boards |
| `miro.boards.get` | Get board details |
| `miro.boards.create` | Create board |
| `miro.boards.update` | Update board |
| `miro.boards.delete` | Delete board |
| `miro.boards.copy` | Copy board |
| `miro.boards.members` | List board members |
| `miro.boards.share` | Share board |
| `miro.users.me` | Get current user |
| `miro.items.list` | List board items |
| `miro.items.get` | Get item details |
| `miro.items.delete` | Delete item |
| `miro.sticky_notes.bulk_create` | Create sticky notes |
| `miro.text.bulk_create` | Create text items |
| `miro.shapes.bulk_create` | Create shapes |
| `miro.cards.bulk_create` | Create cards |
| `miro.connectors.bulk_create` | Create connectors |

### Figma Tools
| Tool | Description |
|------|-------------|
| `figma.dev.get_page` | Extract CSS-ready layout |
| `figma.files.get_layout` | Get compact layout tree |
| `figma.users.me` | Get current user |
| `figma.files.get_meta` | Get file metadata |
| `figma.files.get` | Raw file JSON (use with care) |
| `figma.files.get_nodes` | Raw node JSON |
| `figma.images.export` | Export nodes as images |
| `figma.images.get_fills` | Get image fill URLs |
| `figma.files.versions` | List file versions |
| `figma.comments.list` | List comments |
| `figma.comments.create` | Create comment |
| `figma.comments.delete` | Delete comment |
| `figma.projects.list` | List team projects |
| `figma.projects.files` | List files in a project |
| `figma.components.list_team` | List team components |
| `figma.components.list_file` | List file components |
| `figma.components.get` | Get component |
| `figma.styles.list_team` | List team styles |
| `figma.styles.list_file` | List file styles |
| `figma.styles.get` | Get style |

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ChatGPT       │     │  Claude Desktop │     │     Cursor      │
│   (OAuth 2.0)   │     │  (Bearer Token) │     │  (Bearer Token) │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │       MCP Hub          │
                    │  ┌──────────────────┐  │
                    │  │  OAuth Server    │  │
                    │  │  (RFC 8414)      │  │
                    │  └──────────────────┘  │
                    │  ┌──────────────────┐  │
                    │  │  MCP Gateway     │  │
                    │  │  (JSON-RPC 2.0)  │  │
                    │  └──────────────────┘  │
                    │  ┌──────────────────┐  │
                    │  │  Audit Logger    │  │
                    │  └──────────────────┘  │
                    └────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Teamwork      │     │     Slack       │     │    Telegram     │
│   (OAuth 2.0)   │     │   (OAuth 2.0)   │     │   (MTProto)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

---

## Database

MCP Hub uses SQLite for simplicity and portability. The database is automatically created and migrated on startup.

**Location**: `DATABASE_PATH` (default: `data/app.db`)

**Tables**:
- `users` — User accounts and roles
- `connections` — OAuth tokens (encrypted) and connection metadata
- `refresh_tokens` — JWT refresh tokens
- `personal_access_tokens` — Long-lived PAT tokens
- `api_clients` — Client credentials for OAuth
- `audit_logs` — Tool call audit trail
- `app_settings` — Admin configuration (public URL, credentials)
- `oauth_states` — Temporary OAuth state tokens

---

## API Documentation

Interactive API docs available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

Key endpoints:
- `POST /auth/login` — User login
- `POST /auth/refresh` — Refresh access token
- `POST /auth/personal_token` — Create PAT
- `GET /integrations` — List integration status
- `POST /mcp` — MCP JSON-RPC endpoint
- `GET /config/mcp` — Get MCP configuration
- `GET /.well-known/oauth-authorization-server` — OAuth metadata (RFC 8414)

---

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Code Style

```bash
ruff check app/
ruff format app/
```

### Adding New Integrations

1. Create a new folder in `app/integrations/your_integration/`
2. Implement the `BaseIntegration` interface
3. Define tools in a `tools.py` file
4. Register in `app/integrations/registry.py`

---

## Troubleshooting

### "Invalid or expired refresh token"
- Session may have expired. Log out and log in again.
- Check that your server time is synchronized (NTP).

### OAuth callback fails
- Verify `PUBLIC_BASE_URL` is set correctly in Admin → Settings
- Ensure the callback URL is registered in your OAuth app settings

### Telegram connection fails
- Make sure `TELEGRAM_API_ID` and `TELEGRAM_API_HASH` are set
- Check that your phone number format is correct (with country code)

### ChatGPT can't connect
- Verify your server is accessible from the internet
- Check that `/.well-known/oauth-authorization-server` returns valid JSON
- Ensure CORS headers allow ChatGPT's domain

---

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/mcp_hub/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/mcp_hub/discussions)

---

**MCP Hub** — Connect your tools. Supercharge your AI.
