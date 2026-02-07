CREATE TABLE memory_items (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    type        TEXT NOT NULL,
    scope       TEXT NOT NULL DEFAULT 'global',
    title       TEXT NOT NULL,
    value_json  TEXT NOT NULL DEFAULT '{}',
    tags_json   TEXT NOT NULL DEFAULT '[]',
    pinned      INTEGER NOT NULL DEFAULT 0,
    ttl_days    INTEGER,
    sensitivity TEXT NOT NULL DEFAULT 'low',
    confidence  REAL NOT NULL DEFAULT 1.0,
    source_json TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    version     INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_user_id ON memory_items(user_id);
CREATE INDEX idx_memory_user_type ON memory_items(user_id, type);
CREATE INDEX idx_memory_user_scope ON memory_items(user_id, scope);
CREATE INDEX idx_memory_user_pinned ON memory_items(user_id, pinned);
CREATE UNIQUE INDEX idx_memory_unique_key ON memory_items(user_id, type, scope, title);

CREATE VIRTUAL TABLE memory_items_fts USING fts5(
    title, value_text, tags_text,
    content=memory_items,
    content_rowid=rowid
);

CREATE TRIGGER memory_ai AFTER INSERT ON memory_items BEGIN
    INSERT INTO memory_items_fts(rowid, title, value_text, tags_text)
    VALUES (new.rowid, new.title, new.value_json, new.tags_json);
END;

CREATE TRIGGER memory_ad AFTER DELETE ON memory_items BEGIN
    INSERT INTO memory_items_fts(memory_items_fts, rowid, title, value_text, tags_text)
    VALUES('delete', old.rowid, old.title, old.value_json, old.tags_json);
END;

CREATE TRIGGER memory_au AFTER UPDATE ON memory_items BEGIN
    INSERT INTO memory_items_fts(memory_items_fts, rowid, title, value_text, tags_text)
    VALUES('delete', old.rowid, old.title, old.value_json, old.tags_json);
    INSERT INTO memory_items_fts(rowid, title, value_text, tags_text)
    VALUES (new.rowid, new.title, new.value_json, new.tags_json);
END;
