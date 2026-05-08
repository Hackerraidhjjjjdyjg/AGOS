-- AGOS Database Migrations
-- Migration 001: Initial Schema
-- Tool: Manual SQL (production: use goose/flyway)

-- UP
BEGIN;

-- Track schema version
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Insert migration record
INSERT INTO schema_migrations (version, name) VALUES (1, 'initial_schema')
ON CONFLICT DO NOTHING;

-- Multi-tenancy: Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;

-- RLS Policies (tenant isolation)
CREATE POLICY tenant_isolation_tasks ON tasks
    USING (org_id = current_setting('app.current_org_id', TRUE)::UUID);

CREATE POLICY tenant_isolation_agents ON agents
    USING (org_id = current_setting('app.current_org_id', TRUE)::UUID);

CREATE POLICY tenant_isolation_audit ON audit_log
    USING (org_id = current_setting('app.current_org_id', TRUE)::UUID);

-- Performance indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX IF NOT EXISTS idx_tasks_created_desc ON tasks(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);
CREATE INDEX IF NOT EXISTS idx_audit_time_desc ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usage_org_period ON usage_records(org_id, recorded_at);

-- Session cleanup function
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void AS $$
BEGIN
    DELETE FROM sessions WHERE expires_at < NOW();
END;
$$ LANGUAGE plpgsql;

COMMIT;
