-- =========================================================
-- FOX-KRİPTO MULTI-TENANT SUPABASE POSTGRESQL ŞEMASI
-- =========================================================

-- 1. Kullanıcılar / Kiracılar (Tenants) Tablosu
CREATE TABLE IF NOT EXISTS user_tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_name VARCHAR(100) NOT NULL,
    telegram_chat_id BIGINT UNIQUE NOT NULL,
    exchange_id VARCHAR(30) DEFAULT 'binance',
    exchange_api_key TEXT NOT NULL,
    exchange_secret_key TEXT NOT NULL,
    max_budget_percent NUMERIC(5,2) DEFAULT 10.0,
    stop_loss_percent NUMERIC(5,2) DEFAULT 4.0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. İşlem Kararları ve İnfaz Logları (Tenant Bağlantılı)
CREATE TABLE IF NOT EXISTS crypto_trade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES user_tenants(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL CHECK (direction IN ('BUY', 'SELL', 'LONG', 'SHORT')),
    amount_usd NUMERIC(14, 2) NOT NULL,
    entry_price NUMERIC(18, 8),
    stop_loss_price NUMERIC(18, 8),
    take_profit_price NUMERIC(18, 8),
    sentiment_score NUMERIC(5, 2),
    human_approval VARCHAR(20) DEFAULT 'Pending' CHECK (human_approval IN ('Pending', 'Approved', 'Rejected')),
    status VARCHAR(50) DEFAULT 'CREATED',
    order_id VARCHAR(100),
    execution_details JSONB
);

-- 3. LangGraph State Kalıcılık (Tenant Bağlantılı)
CREATE TABLE IF NOT EXISTS crypto_agent_states (
    session_id VARCHAR(100) PRIMARY KEY,
    tenant_id UUID REFERENCES user_tenants(id),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    state_data JSONB NOT NULL
);

-- RLS Güvenlik Politikaları
ALTER TABLE user_tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE crypto_trade_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE crypto_agent_states ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service Role full access to user_tenants" ON user_tenants FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service Role full access to crypto_trade_logs" ON crypto_trade_logs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service Role full access to crypto_agent_states" ON crypto_agent_states FOR ALL USING (true) WITH CHECK (true);
