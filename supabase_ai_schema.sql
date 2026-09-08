-- FOX-KRİPTO: OPENROUTER AI MODEL REGISTRY & AUDIT SCHEMA (Section 7 & 8)
-- Geriye dönük uyumlu Supabase PostgreSQL migration

-- 1. ai_model_registry: Kayıtlı AI modelleri ve yetenekleri
CREATE TABLE IF NOT EXISTS ai_model_registry (
    id TEXT PRIMARY KEY, -- örn: 'z-ai/glm-5.3-flash', 'google/gemini-3.7-flash', 'openai/gpt-6-astra'
    openrouter_model_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    capabilities JSONB DEFAULT '[]'::jsonb,
    supports_tools BOOLEAN DEFAULT FALSE,
    supports_structured_output BOOLEAN DEFAULT TRUE,
    supports_json_schema BOOLEAN DEFAULT TRUE,
    context_length INTEGER DEFAULT 128000,
    cost_per_1k_input_tokens NUMERIC(10, 6) DEFAULT 0.0001,
    cost_per_1k_output_tokens NUMERIC(10, 6) DEFAULT 0.0002,
    enabled BOOLEAN DEFAULT TRUE,
    deprecated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. ai_role_routes: Rol bazlı model rotaları ve parametreleri
CREATE TABLE IF NOT EXISTS ai_role_routes (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default_tenant',
    role TEXT NOT NULL, -- 'ROUTINE_REPORTING', 'CRITICAL_NEWS_ANALYSIS', 'TECHNICAL_SECOND_OPINION', 'NIGHTLY_FORENSIC_AUDIT', 'CRITICAL_INCIDENT_REVIEW'
    primary_model_id TEXT NOT NULL,
    fallback_model_ids JSONB DEFAULT '[]'::jsonb,
    timeout_ms INTEGER DEFAULT 15000,
    max_retries INTEGER DEFAULT 2,
    max_input_tokens INTEGER DEFAULT 4000,
    max_output_tokens INTEGER DEFAULT 1500,
    daily_call_limit INTEGER DEFAULT 500,
    daily_cost_limit_usd NUMERIC(10, 4) DEFAULT 5.0,
    execution_authority TEXT NOT NULL DEFAULT 'NONE', -- 'NONE', 'BLOCK_ONLY'
    enabled BOOLEAN DEFAULT TRUE,
    version TEXT DEFAULT 'v1.0',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_tenant_role UNIQUE (tenant_id, role)
);

-- 3. ai_prompt_versions: Versiyonlanmış sistem ve kullanıcı promptları
CREATE TABLE IF NOT EXISTS ai_prompt_versions (
    prompt_id TEXT PRIMARY KEY, -- örn: 'critical-news-v1', 'opinion-v2.4', 'nightly-audit-v1'
    role TEXT NOT NULL,
    version TEXT NOT NULL,
    system_prompt_template TEXT NOT NULL,
    schema_definition JSONB,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. ai_call_logs: Her AI çağrısının maliyet, gecikme ve model kaydı
CREATE TABLE IF NOT EXISTS ai_call_logs (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default_tenant',
    user_id TEXT,
    signal_id TEXT,
    trade_id TEXT,
    role TEXT NOT NULL,
    requested_model TEXT NOT NULL,
    resolved_model TEXT NOT NULL,
    provider TEXT,
    fallback_used BOOLEAN DEFAULT FALSE,
    prompt_version TEXT,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    estimated_cost_usd NUMERIC(10, 6) DEFAULT 0.0,
    latency_ms INTEGER DEFAULT 0,
    status TEXT NOT NULL, -- 'SUCCESS', 'FALLBACK_SUCCESS', 'ERROR_TIMEOUT', 'ERROR_PARSE', 'FAIL_CLOSED'
    error_code TEXT,
    schema_valid BOOLEAN DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast tenant usage querying
CREATE INDEX IF NOT EXISTS idx_ai_call_logs_tenant_created ON ai_call_logs (tenant_id, created_at);

-- 5. ai_usage_ledger: Günlük kümülatif harcama defteri
CREATE TABLE IF NOT EXISTS ai_usage_ledger (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    total_calls INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10, 4) DEFAULT 0.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_tenant_date UNIQUE (tenant_id, usage_date)
);

-- 6. ai_budget_limits: Tenant bütçe limitleri (Section 8)
CREATE TABLE IF NOT EXISTS ai_budget_limits (
    tenant_id TEXT PRIMARY KEY,
    daily_ai_budget_usd NUMERIC(10, 2) DEFAULT 5.0,
    monthly_ai_budget_usd NUMERIC(10, 2) DEFAULT 50.0,
    critical_model_budget_usd NUMERIC(10, 2) DEFAULT 10.0,
    max_calls_per_signal INTEGER DEFAULT 2,
    max_calls_per_symbol_per_hour INTEGER DEFAULT 5,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. ai_model_evaluations: Benchmark ve adli değerlendirme sonuçları
CREATE TABLE IF NOT EXISTS ai_model_evaluations (
    id BIGSERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default_tenant',
    evaluation_type TEXT NOT NULL, -- 'NIGHTLY_AUDIT', 'SHADOW_AB_TEST', 'INCIDENT_REVIEW'
    model_id TEXT NOT NULL,
    summary_report TEXT,
    findings JSONB DEFAULT '{}'::jsonb,
    recommendations JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Varsayılan Model Kayıtları (Section 3)
INSERT INTO ai_model_registry (id, openrouter_model_id, display_name, provider, cost_per_1k_input_tokens, cost_per_1k_output_tokens)
VALUES
    ('z-ai/glm-5.3-flash', 'z-ai/glm-5.3-flash', 'GLM-5.3 Flash (Fiyat/Performans)', 'Zhipu/OpenRouter', 0.0001, 0.0002),
    ('nvidia/nemotron-3.5-lightning', 'nvidia/nemotron-3.5-lightning', 'Nemotron 3.5 Lightning (Fallback)', 'Nvidia/OpenRouter', 0.0001, 0.0002),
    ('google/gemini-3.7-flash', 'google/gemini-3.7-flash', 'Gemini 3.7 Flash (Kritik Haber)', 'Google/OpenRouter', 0.0005, 0.0015),
    ('z-ai/glm-5.3', 'z-ai/glm-5.3', 'GLM-5.3 Quant (Shadow Teknik Görüş)', 'Zhipu/OpenRouter', 0.0005, 0.0010),
    ('openai/gpt-6-astra:batch', 'openai/gpt-6-astra:batch', 'GPT-6 Astra Batch (Adli İnceleme)', 'OpenAI/OpenRouter', 0.0050, 0.0150),
    ('openai/gpt-6-astra', 'openai/gpt-6-astra', 'GPT-6 Astra (Manuel Olay İncelemesi)', 'OpenAI/OpenRouter', 0.0100, 0.0300)
ON CONFLICT (id) DO UPDATE SET updated_at = NOW();

-- Varsayılan Rol Rotaları (Section 3)
INSERT INTO ai_role_routes (tenant_id, role, primary_model_id, fallback_model_ids, execution_authority)
VALUES
    ('default_tenant', 'ROUTINE_REPORTING', 'z-ai/glm-5.3-flash', '["nvidia/nemotron-3.5-lightning"]'::jsonb, 'NONE'),
    ('default_tenant', 'CRITICAL_NEWS_ANALYSIS', 'google/gemini-3.7-flash', '["z-ai/glm-5.3"]'::jsonb, 'BLOCK_ONLY'),
    ('default_tenant', 'TECHNICAL_SECOND_OPINION', 'z-ai/glm-5.3', '["google/gemini-3.7-flash"]'::jsonb, 'NONE'),
    ('default_tenant', 'NIGHTLY_FORENSIC_AUDIT', 'openai/gpt-6-astra:batch', '["z-ai/glm-5.3"]'::jsonb, 'NONE'),
    ('default_tenant', 'CRITICAL_INCIDENT_REVIEW', 'openai/gpt-6-astra', '[]'::jsonb, 'NONE')
ON CONFLICT (tenant_id, role) DO UPDATE SET updated_at = NOW();
