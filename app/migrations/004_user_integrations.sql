-- Per-user integration dashboard + custom MCP servers

CREATE TABLE IF NOT EXISTS user_integrations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    provider    TEXT NOT NULL,
    is_enabled  INTEGER NOT NULL DEFAULT 1,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, provider),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_integrations_user ON user_integrations(user_id);
CREATE INDEX IF NOT EXISTS idx_user_integrations_user_enabled ON user_integrations(user_id, is_enabled);

CREATE TABLE IF NOT EXISTS custom_mcp_servers (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL,
    slug             TEXT NOT NULL,
    display_name     TEXT NOT NULL,
    server_url       TEXT NOT NULL,
    auth_type        TEXT NOT NULL DEFAULT 'none',
    auth_secret_enc  TEXT,
    auth_header_name TEXT,
    is_enabled       INTEGER NOT NULL DEFAULT 1,
    health_status    TEXT NOT NULL DEFAULT 'unknown',
    last_health_check TEXT,
    tools_cache_json TEXT,
    tools_cached_at  TEXT,
    meta_json        TEXT,
    created_at       TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, slug),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_custom_mcp_user ON custom_mcp_servers(user_id);
CREATE INDEX IF NOT EXISTS idx_custom_mcp_user_enabled ON custom_mcp_servers(user_id, is_enabled);

-- Backfill: create user_integrations rows for existing connections
INSERT OR IGNORE INTO user_integrations (user_id, provider, is_enabled, position)
SELECT DISTINCT user_id, provider, 1, 0
FROM connections
WHERE is_connected = 1;

-- Add memory integration for all existing users
INSERT OR IGNORE INTO user_integrations (user_id, provider, is_enabled, position)
SELECT id, 'memory', 1, 0
FROM users;
