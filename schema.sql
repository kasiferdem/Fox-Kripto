-- =========================================================
-- FOX-KRİPTO SUPABASE POSTGRESQL VERİTABANI ŞEMASI (STEP 2)
-- =========================================================

-- 1. İşlem Kararları ve İnfaz Logları Tablosu
CREATE TABLE IF NOT EXISTS crypto_trade_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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

-- 2. LangGraph State Kalıcılık (Persistence) Tablosu
CREATE TABLE IF NOT EXISTS crypto_agent_states (
    session_id VARCHAR(100) PRIMARY KEY,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    state_data JSONB NOT NULL
);

-- RLS Güvenlik Politikaları (Service Role yetkili erişim)
ALTER TABLE crypto_trade_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE crypto_agent_states ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service Role full access to crypto_trade_logs" 
ON crypto_trade_logs FOR ALL 
USING (true) WITH CHECK (true);

CREATE POLICY "Service Role full access to crypto_agent_states" 
ON crypto_agent_states FOR ALL 
USING (true) WITH CHECK (true);
