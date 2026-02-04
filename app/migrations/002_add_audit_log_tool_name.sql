ALTER TABLE audit_logs ADD COLUMN tool_name TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_logs_tool_name ON audit_logs(tool_name);
