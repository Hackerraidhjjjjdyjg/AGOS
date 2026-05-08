-- AGOS — PostgreSQL Database Schema
-- Enterprise-grade schema for users, organizations, agents, tasks, audit, and billing.
-- Run: psql -U agos -d agos_db -f schema.sql

-- ─── Extensions ───────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ─── Users ────────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255),                          -- bcrypt hash (null if OAuth-only)
    display_name    VARCHAR(128) NOT NULL,
    avatar_url      TEXT,
    auth_provider   VARCHAR(32) DEFAULT 'local',           -- local, google, apple, github
    auth_provider_id VARCHAR(255),                         -- OAuth provider user ID
    role            VARCHAR(32) DEFAULT 'user',            -- admin, user, viewer, developer
    tier            VARCHAR(32) DEFAULT 'free',            -- free, pro, enterprise
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_provider ON users(auth_provider, auth_provider_id);

-- ─── Organizations (Multi-Tenancy) ───────────────────────────────
CREATE TABLE organizations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(128) NOT NULL,
    slug            VARCHAR(64) UNIQUE NOT NULL,       -- URL-safe identifier
    owner_id        UUID REFERENCES users(id) ON DELETE SET NULL,
    tier            VARCHAR(32) DEFAULT 'free',
    max_agents      INTEGER DEFAULT 5,
    max_tokens_per_day BIGINT DEFAULT 100000,
    settings        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Organization Members ─────────────────────────────────────────
CREATE TABLE org_members (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    role            VARCHAR(32) DEFAULT 'member',      -- owner, admin, member, viewer
    invited_by      UUID REFERENCES users(id),
    joined_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, user_id)
);

CREATE INDEX idx_org_members_org ON org_members(org_id);
CREATE INDEX idx_org_members_user ON org_members(user_id);

-- ─── API Keys ─────────────────────────────────────────────────────
CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
    key_hash        VARCHAR(255) NOT NULL,             -- SHA-256 of the actual key
    key_prefix      VARCHAR(12) NOT NULL,              -- First 8 chars for identification
    name            VARCHAR(128) NOT NULL,
    scopes          TEXT[] DEFAULT '{}',                -- allowed scopes
    rate_limit_rpm  INTEGER DEFAULT 60,                -- requests per minute
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_api_keys_prefix ON api_keys(key_prefix);
CREATE INDEX idx_api_keys_user ON api_keys(user_id);

-- ─── Agents ───────────────────────────────────────────────────────
CREATE TABLE agents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name            VARCHAR(128) NOT NULL,
    type            VARCHAR(64) NOT NULL,              -- orchestrator, system, research, code, custom
    model           VARCHAR(64) NOT NULL DEFAULT 'llama3',
    priority        SMALLINT DEFAULT 2,                -- 0=critical, 4=background
    token_budget    INTEGER DEFAULT 4096,
    capabilities    TEXT[] DEFAULT '{}',
    config          JSONB DEFAULT '{}',                -- Agent-specific configuration
    status          VARCHAR(32) DEFAULT 'idle',        -- idle, running, suspended, failed
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agents_org ON agents(org_id);
CREATE INDEX idx_agents_status ON agents(status);

-- ─── Tasks ────────────────────────────────────────────────────────
CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    agent_id        UUID REFERENCES agents(id) ON DELETE SET NULL,
    parent_task_id  UUID REFERENCES tasks(id),         -- For decomposed subtasks
    intent          TEXT NOT NULL,                      -- Original user request
    status          VARCHAR(32) DEFAULT 'pending',     -- pending, running, completed, failed, cancelled
    priority        SMALLINT DEFAULT 2,
    result          JSONB,                             -- Task output
    error           TEXT,
    tokens_used     INTEGER DEFAULT 0,
    latency_ms      INTEGER,                           -- Total execution time
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tasks_org ON tasks(org_id);
CREATE INDEX idx_tasks_user ON tasks(user_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at DESC);

-- ─── Tool Calls (Every Agent Action) ──────────────────────────────
CREATE TABLE tool_calls (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         UUID REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id        UUID REFERENCES agents(id) ON DELETE SET NULL,
    tool            VARCHAR(128) NOT NULL,
    args            JSONB DEFAULT '{}',
    result          TEXT,
    status          VARCHAR(32) DEFAULT 'success',     -- success, failed, blocked
    risk_level      VARCHAR(16),
    latency_ms      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_tool_calls_task ON tool_calls(task_id);
CREATE INDEX idx_tool_calls_tool ON tool_calls(tool);
CREATE INDEX idx_tool_calls_created ON tool_calls(created_at DESC);

-- ─── Audit Log (Security Compliance) ──────────────────────────────
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID REFERENCES organizations(id),
    user_id         UUID REFERENCES users(id),
    agent_id        UUID REFERENCES agents(id),
    action          VARCHAR(128) NOT NULL,             -- auth.login, agent.execute, tool.blocked
    resource        VARCHAR(128),                      -- What was acted on
    details         JSONB DEFAULT '{}',
    ip_address      INET,
    user_agent      TEXT,
    decision        VARCHAR(16),                       -- allowed, blocked, error
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_org ON audit_log(org_id);
CREATE INDEX idx_audit_action ON audit_log(action);
CREATE INDEX idx_audit_created ON audit_log(created_at DESC);

-- ─── Billing & Usage ──────────────────────────────────────────────
CREATE TABLE billing_accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE UNIQUE,
    stripe_customer_id VARCHAR(128),
    stripe_subscription_id VARCHAR(128),
    plan            VARCHAR(32) DEFAULT 'free',        -- free, pro, enterprise
    tokens_used_today BIGINT DEFAULT 0,
    tokens_used_month BIGINT DEFAULT 0,
    tokens_limit    BIGINT DEFAULT 100000,             -- Daily limit
    billing_email   VARCHAR(255),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE usage_records (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID REFERENCES organizations(id),
    user_id         UUID REFERENCES users(id),
    agent_id        UUID REFERENCES agents(id),
    task_id         UUID REFERENCES tasks(id),
    tokens_used     INTEGER NOT NULL,
    model           VARCHAR(64),
    cost_usd        DECIMAL(10, 6),                    -- Estimated cost
    recorded_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_usage_org_date ON usage_records(org_id, recorded_at DESC);

-- ─── Sessions (JWT Refresh Tokens) ────────────────────────────────
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash VARCHAR(255) NOT NULL,
    device_info     JSONB,
    ip_address      INET,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

-- ─── Agent Memory (Knowledge Base) ───────────────────────────────
CREATE TABLE knowledge_entries (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID REFERENCES organizations(id) ON DELETE CASCADE,
    agent_id        UUID REFERENCES agents(id),
    category        VARCHAR(64),                       -- fact, procedure, episode
    content         TEXT NOT NULL,
    embedding_id    VARCHAR(128),                      -- ChromaDB document ID
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_knowledge_org ON knowledge_entries(org_id);
CREATE INDEX idx_knowledge_category ON knowledge_entries(category);

-- ─── Seed Data ────────────────────────────────────────────────────
INSERT INTO users (email, display_name, role, tier, is_verified) 
VALUES ('admin@agos.ai', 'AGOS Admin', 'admin', 'enterprise', TRUE);
