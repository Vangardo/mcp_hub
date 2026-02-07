# MCP Hub

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-0db7ed.svg)](docker/)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg)](https://fastapi.tiangolo.com/)

**MCP Hub** is a self-hosted, multi-user gateway that connects **7 integrations** and **130+ tools** to AI assistants via the **Model Context Protocol (MCP)**.

One server. One endpoint. **Teamwork**, **Slack**, **Telegram**, **Miro**, **Figma**, **Binance**, and built-in **Memory** — all accessible from **Claude Desktop**, **ChatGPT**, **Cursor**, or any MCP-compatible client.

---

## Why MCP Hub?

| Problem | Solution |
|---------|----------|
| Each integration needs its own MCP server | Single gateway for everything |
| AI can't remember context between sessions | Built-in Memory provider with FTS5 search |
| Token security concerns | AES-256 encrypted storage, tokens never exposed to AI |
| No visibility into what AI does | Full audit trail — every tool call logged |
| Team needs shared access | Multi-user with admin approval, per-user connections |
| Complex deployment | Single Docker container, SQLite, zero external deps |

---

## Integrations & Tools Overview

| Integration | Auth | Tools | What it does |
|-------------|------|------:|--------------|
| **Teamwork** | OAuth 2.0 | 45 | Projects, tasks, subtasks, dependencies, time tracking, tags, comments, board management |
| **Miro** | OAuth 2.0 | 17 | Boards, sticky notes, text, shapes, cards, connectors |
| **Slack** | OAuth 2.0 | 18 | Channels, messages, DMs, user lookup, canvases |
| **Figma** | OAuth 2.0 | 16 | CSS extraction, layout trees, images, comments, components, styles |
| **Binance** | API Key | 11 | Market data with indicators (RSI, MACD, Bollinger), order book, spot trading, portfolio |
| **Telegram** | MTProto | 5 | Dialogs, messages, search, history |
| **Memory** | Built-in | 7 | Persistent AI memory — preferences, goals, watchlists, notes with FTS5 search |
| **Hub** | — | 3 | Integration discovery & tool routing |
| | | **122** | |

---

## How It Works

AI clients interact with MCP Hub through a **3-step discovery pattern**:

```
Step 1: hub.integrations.list  →  "What integrations are available?"
Step 2: hub.tools.list         →  "What can Teamwork do?"
Step 3: hub.tools.call         →  "Create a task in project X"
```

```
┌──────────────────────────────────────────────────────────┐
│              AI Client (Claude / ChatGPT / Cursor)       │
└──────────────────────┬───────────────────────────────────┘
                       │ JSON-RPC 2.0 + Bearer Token
                       ▼
┌──────────────────────────────────────────────────────────┐
│                      MCP Hub                             │
│                                                          │
│   ┌──────────┐  ┌───────────┐  ┌──────────┐            │
│   │ OAuth 2.0│  │MCP Gateway│  │  Audit   │            │
│   │ Server   │  │ (Router)  │  │  Logger  │            │
│   └──────────┘  └─────┬─────┘  └──────────┘            │
│                       │                                  │
│   ┌───────┬───────┬───┴───┬────────┬─────────┬───────┐  │
│   │Slack  │Miro   │Figma  │Teamwork│Binance  │Memory │  │
│   │18     │17     │16     │45      │11       │7      │  │
│   │tools  │tools  │tools  │tools   │tools    │tools  │  │
│   └───────┴───────┴───────┴────────┴─────────┴───────┘  │
│                                                          │
│   ┌──────────────────────────────────────────────────┐   │
│   │  SQLite + FTS5  │  Encrypted Tokens  │  Migrations│  │
│   └──────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Docker (Recommended)

```bash
git clone https://github.com/Vangardo/mcp_hub.git
cd mcp_hub

cp .env.example .env
nano .env  # Set ADMIN_EMAIL, ADMIN_PASSWORD, JWT_SECRET, TOKENS_ENCRYPTION_KEY

cd docker
docker-compose up -d

# Open http://localhost:8000
```

### Local Development

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
nano .env

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Connecting AI Clients

### Claude Desktop

Generate a **Personal Access Token** in MCP Hub, then add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "mcp-hub": {
      "url": "https://your-domain.com/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_PAT_TOKEN"
      }
    }
  }
}
```

### ChatGPT (Actions)

1. Click **Get GPT Config** in MCP Hub
2. Use the **OAuth** tab — ChatGPT auto-discovers endpoints via RFC 8414
3. Server URL: `https://your-domain.com/mcp`

### Cursor / Other MCP Clients

Same as Claude Desktop — Bearer token + MCP endpoint URL.

---

## All Tools Reference

### Hub (3 tools)

| Tool | Description |
|------|-------------|
| `hub.integrations.list` | List connected integrations. Set `include_tools=true` for full tool catalog |
| `hub.tools.list` | List tools for a specific provider |
| `hub.tools.call` | Execute a tool. Pass `provider`, `tool_name`, and `arguments` |

### Teamwork (45 tools)

<details>
<summary>Projects & People</summary>

| Tool | Description |
|------|-------------|
| `teamwork.projects.list` | List all projects |
| `teamwork.people.list` | List team members |
| `teamwork.people.me` | Get current user |
</details>

<details>
<summary>Tasks — Read</summary>

| Tool | Description |
|------|-------------|
| `teamwork.tasks.list` | List tasks with filters (status, assignee, due date, tags) |
| `teamwork.tasks.get` | Get full task details by ID |
| `teamwork.tasks.due_today` | Tasks due today |
| `teamwork.tasks.overdue` | Overdue tasks |
| `teamwork.tasks.actionable` | Unblocked tasks ready to work on |
| `teamwork.tasks.blocked` | Tasks blocked by dependencies |
</details>

<details>
<summary>Tasks — Create & Update</summary>

| Tool | Description |
|------|-------------|
| `teamwork.tasks.bulk_create` | Create up to 10 tasks with subtasks, dependencies, and tags |
| `teamwork.tasks.bulk_update` | Update up to 10 tasks at once |
| `teamwork.tasks.complete` | Mark task as complete |
</details>

<details>
<summary>Task Lists</summary>

| Tool | Description |
|------|-------------|
| `teamwork.tasklists.list` | List task lists in a project |
| `teamwork.tasklists.get` | Get list details |
| `teamwork.tasklists.create` | Create new list |
| `teamwork.tasklists.update` | Update list |
| `teamwork.tasklists.delete` | Delete list |
| `teamwork.tasklists.copy` | Copy list to another project |
| `teamwork.tasklists.move` | Move list to another project |
</details>

<details>
<summary>Subtasks & Dependencies</summary>

| Tool | Description |
|------|-------------|
| `teamwork.subtasks.create` | Create subtask under parent |
| `teamwork.subtasks.list` | List subtasks |
| `teamwork.dependencies.get` | Get predecessors & dependents |
| `teamwork.dependencies.set` | Replace all predecessors |
| `teamwork.dependencies.add` | Add one predecessor |
| `teamwork.dependencies.remove` | Remove one predecessor |
| `teamwork.dependencies.clear` | Remove all predecessors |
| `teamwork.dependencies.bulk_set` | Set dependencies for up to 10 tasks |
</details>

<details>
<summary>Time Tracking</summary>

| Tool | Description |
|------|-------------|
| `teamwork.time.log` | Log time entry |
| `teamwork.time.list` | List time entries |
| `teamwork.time.totals` | Get time totals for reporting |
</details>

<details>
<summary>Tags, Comments & Board</summary>

| Tool | Description |
|------|-------------|
| `teamwork.tags.list` | List all tags |
| `teamwork.tags.ensure` | Get or create tag by name |
| `teamwork.tags.create` | Create tag |
| `teamwork.tags.update` | Update tag |
| `teamwork.tags.delete` | Delete tag |
| `teamwork.comments.add` | Add comment to task |
| `teamwork.comments.list` | List task comments |
| `teamwork.workflows.list` | List workflow stages |
| `teamwork.stages.list` | List board columns |
| `teamwork.columns.list` | List board columns (alias) |
| `teamwork.tasks.set_stage` | Move task to stage by ID |
| `teamwork.tasks.set_stage_by_name` | Move task to stage by name |
| `teamwork.tasks.move_to_column` | Move task to column by ID |
| `teamwork.tasks.move_to_column_by_name` | Move task to column by name |
</details>

### Slack (18 tools)

<details>
<summary>Channels & Users</summary>

| Tool | Description |
|------|-------------|
| `slack.channels.list` | List channels (public, private, or filtered) |
| `slack.users.list` | List workspace users |
| `slack.users.me` | Get current user |
| `slack.users.info` | Get user details by ID |
| `slack.users.find_by_email` | Find user by email |
</details>

<details>
<summary>Messages & DMs</summary>

| Tool | Description |
|------|-------------|
| `slack.messages.post` | Post to channel (supports threads) |
| `slack.messages.history` | Get channel message history |
| `slack.dm.list` | List 1:1 DMs |
| `slack.dm.group_list` | List group DMs |
| `slack.dm.send` | Send direct message |
| `slack.dm.history` | Get DM history |
| `slack.dm.open` | Open DM with user |
| `slack.dm.open_group` | Open group DM |
</details>

<details>
<summary>Canvases</summary>

| Tool | Description |
|------|-------------|
| `slack.canvas.create` | Create canvas with markdown |
| `slack.canvas.edit` | Edit content (append/prepend/replace) |
| `slack.canvas.delete` | Delete canvas |
| `slack.canvas.share` | Share with users/channels |
| `slack.canvas.sections_lookup` | Find sections by heading |
</details>

### Miro (17 tools)

<details>
<summary>Boards</summary>

| Tool | Description |
|------|-------------|
| `miro.boards.list` | Search/list boards |
| `miro.boards.get` | Get board details |
| `miro.boards.create` | Create board |
| `miro.boards.update` | Update board |
| `miro.boards.delete` | Delete board |
| `miro.boards.copy` | Copy board with content |
| `miro.boards.members` | List board members & roles |
| `miro.boards.share` | Share with users by email |
| `miro.users.me` | Get current user |
</details>

<details>
<summary>Items & Content</summary>

| Tool | Description |
|------|-------------|
| `miro.items.list` | List items (filter by type) |
| `miro.items.get` | Get item details |
| `miro.items.delete` | Delete item |
| `miro.sticky_notes.bulk_create` | Create up to 10 sticky notes |
| `miro.text.bulk_create` | Create up to 10 text items |
| `miro.shapes.bulk_create` | Create up to 10 shapes (20+ types) |
| `miro.cards.bulk_create` | Create up to 10 cards |
| `miro.connectors.bulk_create` | Create up to 10 connectors |
</details>

### Figma (16 tools)

<details>
<summary>Dev & Layout (primary)</summary>

| Tool | Description |
|------|-------------|
| `figma.dev.get_page` | **Main tool** — extract CSS-ready HTML + design tokens. Overview mode (no node_id) or CSS mode (with node_id) |
| `figma.files.get_layout` | Compact text tree view of file structure |
| `figma.users.me` | Get current user |
| `figma.files.get_meta` | Lightweight file metadata |
</details>

<details>
<summary>Images, Comments & Components</summary>

| Tool | Description |
|------|-------------|
| `figma.images.export` | Export nodes as PNG/SVG/JPG/PDF |
| `figma.images.get_fills` | Get image fill download URLs |
| `figma.files.versions` | List file versions |
| `figma.comments.list` | List comments |
| `figma.comments.create` | Create comment |
| `figma.comments.delete` | Delete comment |
| `figma.projects.list` | List team projects |
| `figma.projects.files` | List files in project |
| `figma.components.list_team` | List published team components |
| `figma.components.list_file` | List file components |
| `figma.components.get` | Get component metadata |
| `figma.styles.list_team` | List published styles |
| `figma.styles.list_file` | List file styles |
| `figma.styles.get` | Get style metadata |
</details>

### Binance (11 tools)

<details>
<summary>Market Data (no signing)</summary>

| Tool | Description |
|------|-------------|
| `binance.market.klines` | OHLCV candles + indicators (RSI 14, MACD 12/26/9, Bollinger 20/2, SMA 20) with AI-friendly interpretations |
| `binance.market.ticker` | 24h price stats. Omit symbol for top 20 by volume |
| `binance.market.depth` | Order book with spread analysis and wall detection |
| `binance.market.top_movers` | Top gainers/losers (filters low-volume pairs) |
</details>

<details>
<summary>Account (signed)</summary>

| Tool | Description |
|------|-------------|
| `binance.account.portfolio` | Spot balances with estimated USD values |
| `binance.account.open_orders` | List unfilled orders |
| `binance.account.trade_history` | Recent executed trades |
</details>

<details>
<summary>Trading (signed, spot only)</summary>

| Tool | Description |
|------|-------------|
| `binance.trade.buy` | Place BUY order (MARKET / LIMIT) |
| `binance.trade.sell` | Place SELL order (MARKET / LIMIT) |
| `binance.trade.cancel` | Cancel order by ID |
| `binance.trade.order_status` | Check order status |
</details>

### Telegram (5 tools)

| Tool | Description |
|------|-------------|
| `telegram.users.me` | Get current user info |
| `telegram.dialogs.list` | List all chats |
| `telegram.messages.send` | Send message |
| `telegram.messages.search` | Search messages |
| `telegram.messages.history` | Get chat history |

### Memory (7 tools)

The Memory provider is **built-in** — always available, no connection needed. It gives AI persistent context across conversations.

| Tool | Description |
|------|-------------|
| `memory.summarize_context` | Load user's context pack: pinned items, preferences, constraints, goals, watchlist, contacts, recent notes. Scope filtering (global / per-integration) |
| `memory.search` | FTS5 full-text search with filters (type, scope, pinned, sensitivity). Supports AND, OR, NOT, phrases |
| `memory.upsert` | Create/update item. Deduplicates by (type + scope + title). Auto-evaluates secrets & sensitivity. Types: `preference`, `constraint`, `decision`, `goal`, `project`, `contact`, `asset`, `note` |
| `memory.delete` | Delete by ID or by title |
| `memory.pin` | Toggle pinned status (pinned items never expire) |
| `memory.set_ttl` | Set expiration: null = permanent, integer = days |
| `memory.evaluate_write` | Pre-save check — detects secrets, validates sensitivity, suggests TTL |

**Auto TTL by type:**
- Permanent: `preference`, `constraint`, `decision`, `asset`, `project`, `contact`
- 30 days: `goal`
- 7 days (or permanent if pinned): `note`

---

## Security

| Feature | Details |
|---------|---------|
| **Token encryption** | AES-256 at rest for all OAuth/API tokens |
| **JWT authentication** | Configurable expiration, refresh token rotation |
| **Personal Access Tokens** | SHA-256 hashed, expiration support, last-used tracking |
| **OAuth 2.0 + PKCE** | Full RFC 8414/7591/9728 for ChatGPT integration |
| **Client Credentials** | Machine-to-machine auth for custom apps |
| **Audit logging** | Every tool call: user, provider, action, request/response, status |
| **Memory safety** | Secret pattern detection blocks auto-saving passwords/keys |
| **Admin approval** | New users require admin approval before access |

---

## Admin Panel

Navigate to **Admin** in the top nav (admin users only):

- **Users** — Approve/reject signups, manage roles, reset passwords, view per-user connections
- **Audit Log** — Filter by user, provider, action, status, date range. Full request/response payloads
- **Settings** — Configure public URL, OAuth credentials for all integrations

---

## Configuration

### Required

```bash
ADMIN_EMAIL=admin@example.com       # Auto-created on first run
ADMIN_PASSWORD=your-secure-password
JWT_SECRET=your-jwt-secret-min-32-chars
TOKENS_ENCRYPTION_KEY=your-32-char-encryption-key
BASE_URL=http://localhost:8000
```

### Integration Credentials (optional — configure per integration)

```bash
# Teamwork (https://developer.teamwork.com/)
TEAMWORK_CLIENT_ID=
TEAMWORK_CLIENT_SECRET=

# Slack (https://api.slack.com/apps)
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=

# Miro (https://miro.com/app/settings/user-profile/apps)
MIRO_CLIENT_ID=
MIRO_CLIENT_SECRET=

# Figma (https://www.figma.com/developers/apps)
FIGMA_CLIENT_ID=
FIGMA_CLIENT_SECRET=

# Telegram (https://my.telegram.org/)
TELEGRAM_API_ID=
TELEGRAM_API_HASH=

# Binance — users connect via their own API Key + Secret in the UI
# No server-side credentials needed
```

Credentials can also be set via **Admin > Settings** in the web UI.

---

## Database

SQLite with automatic migrations on startup.

| Table | Purpose |
|-------|---------|
| `users` | Accounts, roles (admin/user), approval status |
| `connections` | OAuth tokens (encrypted), connection metadata |
| `refresh_tokens` | JWT refresh token rotation |
| `personal_access_tokens` | PAT with hashing & expiration |
| `api_clients` | Client credentials for OAuth apps |
| `audit_logs` | Full tool call audit trail |
| `settings` | Admin configuration (key-value) |
| `memory_items` | AI memory with FTS5 search index |
| `memory_items_fts` | FTS5 virtual table (auto-synced via triggers) |

---

## API Endpoints

Interactive docs at `/docs` (Swagger) and `/redoc`.

| Endpoint | Description |
|----------|-------------|
| `POST /mcp` | MCP JSON-RPC 2.0 gateway |
| `GET /mcp` | SSE endpoint hint |
| `POST /mcp/messages` | SSE-compatible messages |
| `POST /auth/login` | User login |
| `POST /auth/refresh` | Refresh access token |
| `POST /auth/personal_token` | Create PAT |
| `GET /integrations` | List integration status |
| `GET /config/mcp` | Get MCP configuration for AI clients |
| `GET /memory` | Memory management UI |
| `GET /.well-known/oauth-authorization-server` | OAuth 2.0 metadata (RFC 8414) |

---

## Adding New Integrations

1. Create `app/integrations/your_integration/`
2. Implement `BaseIntegration` (see `app/integrations/base.py`):
   - `name`, `display_name`, `description`, `auth_type`
   - `get_tools()` → list of `ToolDefinition`
   - `execute_tool()` → dispatch to tool handlers
3. Define tools in `tools.py` with JSON Schema input definitions
4. Register in `app/integrations/registry.py`
5. Add UI card in `app/ui/templates/integrations.html`

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

**MCP Hub** — One gateway. 7 integrations. 122 tools. Full AI control.
