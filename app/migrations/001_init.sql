PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user',
    is_active       INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'approved',
    rejected_reason TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE refresh_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    token_hash      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    revoked_at      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX idx_refresh_tokens_token_hash ON refresh_tokens(token_hash);

CREATE TABLE oauth_states (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    state       TEXT NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    provider    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_oauth_states_state ON oauth_states(state);

CREATE TABLE connections (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    provider            TEXT NOT NULL,
    auth_type           TEXT NOT NULL,
    is_connected        INTEGER NOT NULL DEFAULT 1,
    secret_enc          TEXT NOT NULL,
    refresh_secret_enc  TEXT,
    expires_at          TEXT,
    scope               TEXT,
    meta_json           TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, provider),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_connections_user_provider ON connections(user_id, provider);

CREATE TABLE audit_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    provider        TEXT,
    action          TEXT NOT NULL,
    request_json    TEXT,
    response_json   TEXT,
    status          TEXT NOT NULL,
    error_text      TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_provider ON audit_logs(provider);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at);

CREATE TABLE app_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE personal_access_tokens (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    token_hash   TEXT NOT NULL,
    name         TEXT,
    expires_at   TEXT NOT NULL,
    last_used_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_personal_tokens_user_id ON personal_access_tokens(user_id);
CREATE INDEX idx_personal_tokens_token_hash ON personal_access_tokens(token_hash);

CREATE TABLE api_clients (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL,
    client_id           TEXT NOT NULL UNIQUE,
    client_secret_hash  TEXT NOT NULL,
    client_secret_enc   TEXT,
    name                TEXT,
    is_active           INTEGER NOT NULL DEFAULT 1,
    last_used_at        TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_api_clients_user_id ON api_clients(user_id);
