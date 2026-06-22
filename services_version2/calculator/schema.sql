-- ================================================================
-- CUSTOMS AI DATABASE SCHEMA
-- ================================================================
-- Database: customs_ai
-- Purpose: Tax calculation system for Cambodia customs duties
-- Last Updated: 2026-03-04
-- ================================================================

-- ================================================================
-- EXTENSIONS
-- ================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ================================================================
-- 1. HS CODES TABLE
-- ================================================================
-- Master table of Harmonized System tariff codes
CREATE TABLE IF NOT EXISTS hs_codes (
    hs_code VARCHAR(15) PRIMARY KEY,
    description TEXT NOT NULL,
    unit VARCHAR(50),
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_hs_active ON hs_codes(is_active, effective_date);
CREATE INDEX idx_hs_code_prefix ON hs_codes(hs_code varchar_pattern_ops);

COMMENT ON TABLE hs_codes IS 'Harmonized System tariff classification codes';
COMMENT ON COLUMN hs_codes.unit IS 'Unit of measurement (kg, pcs, l, etc.)';

-- ================================================================
-- 2. DUTY RATES TABLE
-- ================================================================
-- Tax rates (CD, ST, VAT, ET) by HS code
CREATE TABLE IF NOT EXISTS duty_rates (
    id SERIAL PRIMARY KEY,
    hs_code VARCHAR(15) NOT NULL,
    description TEXT,
    unit VARCHAR(50),
    cd_rate DECIMAL(5,2) DEFAULT 0.00,  -- Customs Duty (%)
    st_rate DECIMAL(5,2) DEFAULT 0.00,  -- Special Tax/Excise (%)
    vat_rate DECIMAL(5,2) DEFAULT 10.00, -- VAT (%)
    et_rate DECIMAL(5,2) DEFAULT 0.00,   -- Export Tax (%)
    atp_rate DECIMAL(10,4) DEFAULT 0.00, -- Additional Tax on Petroleum ($/L)
    origin_country VARCHAR(2) DEFAULT 'XX', -- ISO alpha-2 or XX for general MFN
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (hs_code) REFERENCES hs_codes(hs_code) ON DELETE CASCADE
);

CREATE INDEX idx_duty_hs ON duty_rates(hs_code);
CREATE INDEX idx_duty_active ON duty_rates(is_active, effective_date);
CREATE INDEX idx_duty_origin ON duty_rates(origin_country);

COMMENT ON TABLE duty_rates IS 'Tax rates (CD, ST, VAT, ET, ATP) by HS code and origin country';
COMMENT ON COLUMN duty_rates.cd_rate IS 'Customs Duty rate as percentage (0-100)';
COMMENT ON COLUMN duty_rates.st_rate IS 'Special Tax (Excise) rate as percentage';
COMMENT ON COLUMN duty_rates.vat_rate IS 'Value Added Tax rate (default 10%)';
COMMENT ON COLUMN duty_rates.et_rate IS 'Export Tax rate as percentage';
COMMENT ON COLUMN duty_rates.atp_rate IS 'Additional Tax on Petroleum rate in USD per liter (e.g., 0.02 = $0.02/L)';
COMMENT ON COLUMN duty_rates.origin_country IS 'ISO 3166-1 alpha-2 code; XX = General/MFN rates';

-- ================================================================
-- 3. EXCHANGE RATES TABLE
-- ================================================================
-- Stores currency exchange rates relative to USD and KHR
CREATE TABLE IF NOT EXISTS exchange_rates (
    id SERIAL PRIMARY KEY,
    currency_code VARCHAR(3) NOT NULL,  -- ISO 4217 currency code
    currency_name VARCHAR(100),
    usd_rate DECIMAL(12,4) NOT NULL DEFAULT 1.0000, -- 1 USD = X of this currency
    khr_rate DECIMAL(12,4) NOT NULL,     -- 1 of this currency = X KHR
    effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source VARCHAR(100) DEFAULT 'NBC', -- National Bank of Cambodia
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(currency_code, effective_date)
);

CREATE INDEX idx_exchange_currency ON exchange_rates(currency_code);
CREATE INDEX idx_exchange_date ON exchange_rates(effective_date DESC);

COMMENT ON TABLE exchange_rates IS 'Currency exchange rates from National Bank of Cambodia';
COMMENT ON COLUMN exchange_rates.usd_rate IS '1 USD equals this many units of currency_code';
COMMENT ON COLUMN exchange_rates.khr_rate IS '1 unit of currency_code equals this many KHR';

-- ================================================================
-- 4. DECLARED VALUES TABLE
-- ================================================================
-- Government-published fair market values per metric ton by HS code
-- Used for petroleum, rubber, and FTA/DV cases
CREATE TABLE IF NOT EXISTS declared_values (
    id SERIAL PRIMARY KEY,
    hs_code VARCHAR(15) NOT NULL,
    dv_per_metric_ton DECIMAL(18,4) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    effective_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source VARCHAR(100), -- e.g., "MEF-2026-May"
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(hs_code, effective_date)
);

CREATE INDEX idx_dv_hs ON declared_values(hs_code);
CREATE INDEX idx_dv_active ON declared_values(is_active, effective_date);

COMMENT ON TABLE declared_values IS 'Government-published declared values per metric ton by HS code';
COMMENT ON COLUMN declared_values.dv_per_metric_ton IS 'Fair market price per metric ton for customs valuation';
COMMENT ON COLUMN declared_values.source IS 'Source document, e.g. MEF monthly bulletin';

CREATE TRIGGER update_declared_values_updated_at BEFORE UPDATE ON declared_values
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================================================
-- 5. FEES TABLE
-- ================================================================
-- Stores additional customs fees (scanner, storage, etc.)
CREATE TABLE IF NOT EXISTS fees (
    fee_code VARCHAR(50) PRIMARY KEY,
    fee_name VARCHAR(200) NOT NULL,
    basis VARCHAR(50) NOT NULL, -- 'per container', 'per day', '% of customs value'
    amount DECIMAL(12,2),
    currency VARCHAR(3) DEFAULT 'KHR',
    percentage DECIMAL(5,2), -- For percentage-based fees
    notes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_fees_active ON fees(is_active, effective_date);

COMMENT ON TABLE fees IS 'Additional customs fees (scanner, storage, etc.)';
COMMENT ON COLUMN fees.basis IS 'How the fee is calculated (per container, per day, percentage)';

-- ================================================================
-- 6. EXEMPTIONS TABLE
-- ================================================================
-- Stores exemption regimes and conditions
CREATE TABLE IF NOT EXISTS exemptions (
    exemption_code VARCHAR(50) PRIMARY KEY,
    regime_name VARCHAR(200) NOT NULL,
    exemption_type VARCHAR(50) NOT NULL, -- 'full', 'partial_cd', 'partial_vat', etc.
    cd_exempt BOOLEAN DEFAULT FALSE,
    st_exempt BOOLEAN DEFAULT FALSE,
    vat_exempt BOOLEAN DEFAULT FALSE,
    et_exempt BOOLEAN DEFAULT FALSE,
    cd_reduction_pct DECIMAL(5,2) DEFAULT 0.00,
    vat_reduction_pct DECIMAL(5,2) DEFAULT 0.00,
    conditions TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_exemptions_active ON exemptions(is_active, effective_date);
CREATE INDEX idx_exemptions_type ON exemptions(exemption_type);

COMMENT ON TABLE exemptions IS 'Exemption regimes (DIP, QIP, FTA, etc.)';
COMMENT ON COLUMN exemptions.exemption_type IS 'Type: full, partial_cd, partial_vat, conditional';

-- ================================================================
-- 8. FORMULAS TABLE
-- ================================================================
-- Stores calculation formulas as SQL expressions
CREATE TABLE IF NOT EXISTS formulas (
    formula_id VARCHAR(50) PRIMARY KEY,
    formula_name VARCHAR(200) NOT NULL,
    formula_type VARCHAR(50) NOT NULL, -- 'cif', 'duty', 'vat', 'total', etc.
    expression TEXT NOT NULL,
    description TEXT,
    variables JSONB, -- List of required variables
    is_active BOOLEAN DEFAULT TRUE,
    version INTEGER DEFAULT 1,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_formulas_active ON formulas(is_active, effective_date);
CREATE INDEX idx_formulas_type ON formulas(formula_type);

COMMENT ON TABLE formulas IS 'Calculation formulas stored as executable expressions';
COMMENT ON COLUMN formulas.expression IS 'Python or SQL expression for calculation';

-- ================================================================
-- 9. CALCULATION HISTORY TABLE
-- ================================================================
-- Audit trail of all calculations
CREATE TABLE IF NOT EXISTS calculation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(100),
    hs_code VARCHAR(15),
    origin_country VARCHAR(2),
    invoice_value DECIMAL(15,2),
    invoice_currency VARCHAR(3),
    freight DECIMAL(15,2),
    insurance DECIMAL(15,2),
    cif_value DECIMAL(15,2),
    customs_duty DECIMAL(15,2),
    special_tax DECIMAL(15,2),
    vat DECIMAL(15,2),
    export_tax DECIMAL(15,2),
    total_tax DECIMAL(15,2),
    exemption_code VARCHAR(50),
    calculation_method VARCHAR(50),
    formulas_used JSONB,
    input_data JSONB,
    result_data JSONB,
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    calculated_by VARCHAR(100),
    FOREIGN KEY (hs_code) REFERENCES hs_codes(hs_code) ON DELETE SET NULL,
    FOREIGN KEY (exemption_code) REFERENCES exemptions(exemption_code) ON DELETE SET NULL
);

CREATE INDEX idx_calc_history_hs ON calculation_history(hs_code);
CREATE INDEX idx_calc_history_session ON calculation_history(session_id);
CREATE INDEX idx_calc_history_date ON calculation_history(calculated_at DESC);

COMMENT ON TABLE calculation_history IS 'Audit trail of all tax calculations';

-- ================================================================
-- 10. POLICIES TABLE
-- ================================================================
-- Stores policy rules and business logic
CREATE TABLE IF NOT EXISTS policies (
    policy_id VARCHAR(50) PRIMARY KEY,
    policy_name VARCHAR(200) NOT NULL,
    policy_type VARCHAR(50) NOT NULL, -- 'duty', 'vat', 'exemption', 'validation', etc.
    conditions JSONB NOT NULL, -- Conditions for applying this policy
    actions JSONB NOT NULL, -- Actions to take when conditions met
    priority INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    effective_date DATE DEFAULT CURRENT_DATE,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_policies_active ON policies(is_active, effective_date);
CREATE INDEX idx_policies_type ON policies(policy_type);
CREATE INDEX idx_policies_priority ON policies(priority);

COMMENT ON TABLE policies IS 'Policy rules and business logic for tax calculations';
COMMENT ON COLUMN policies.conditions IS 'JSON conditions: {"hs_code_starts_with": "8471", "origin": "CN"}';
COMMENT ON COLUMN policies.actions IS 'JSON actions: {"apply_exemption": "DIP", "reduce_duty": 50}';

-- ================================================================
-- VIEWS
-- ================================================================

-- View: Current active duty rates
CREATE OR REPLACE VIEW current_duty_rates AS
SELECT 
    dr.hs_code,
    hs.description as hs_description,
    dr.cd_rate,
    dr.st_rate,
    dr.vat_rate,
    dr.et_rate,
    dr.origin_country,
    dr.effective_date
FROM duty_rates dr
JOIN hs_codes hs ON dr.hs_code = hs.hs_code
WHERE dr.is_active = TRUE 
  AND (dr.end_date IS NULL OR dr.end_date > CURRENT_DATE)
  AND hs.is_active = TRUE;

-- View: Current exchange rates
CREATE OR REPLACE VIEW current_exchange_rates AS
SELECT 
    currency_code,
    currency_name,
    usd_rate,
    khr_rate,
    effective_date,
    source
FROM exchange_rates
WHERE effective_date = (
    SELECT MAX(effective_date) 
    FROM exchange_rates e2 
    WHERE e2.currency_code = exchange_rates.currency_code
      AND e2.effective_date <= CURRENT_DATE
);

-- View: Active exemptions
CREATE OR REPLACE VIEW active_exemptions AS
SELECT 
    exemption_code,
    regime_name,
    exemption_type,
    cd_exempt,
    st_exempt,
    vat_exempt,
    et_exempt,
    cd_reduction_pct,
    vat_reduction_pct,
    conditions
FROM exemptions
WHERE is_active = TRUE 
  AND (end_date IS NULL OR end_date > CURRENT_DATE);

-- ================================================================
-- FUNCTIONS
-- ================================================================

-- Function: Get duty rate for HS code and origin
CREATE OR REPLACE FUNCTION get_duty_rate(
    p_hs_code VARCHAR(15),
    p_origin VARCHAR(2) DEFAULT 'XX'
)
RETURNS TABLE (
    hs_code VARCHAR(15),
    cd_rate DECIMAL(5,2),
    st_rate DECIMAL(5,2),
    vat_rate DECIMAL(5,2),
    et_rate DECIMAL(5,2)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        dr.hs_code,
        dr.cd_rate,
        dr.st_rate,
        dr.vat_rate,
        dr.et_rate
    FROM duty_rates dr
    WHERE dr.hs_code = p_hs_code
      AND dr.origin_country = p_origin
      AND dr.is_active = TRUE
      AND (dr.end_date IS NULL OR dr.end_date > CURRENT_DATE)
    ORDER BY dr.effective_date DESC
    LIMIT 1;
    
    -- Fallback to general MFN rates if no country-specific rate found
    IF NOT FOUND THEN
        RETURN QUERY
        SELECT 
            dr.hs_code,
            dr.cd_rate,
            dr.st_rate,
            dr.vat_rate,
            dr.et_rate
        FROM duty_rates dr
        WHERE dr.hs_code = p_hs_code
          AND dr.origin_country = 'XX'
          AND dr.is_active = TRUE
          AND (dr.end_date IS NULL OR dr.end_date > CURRENT_DATE)
        ORDER BY dr.effective_date DESC
        LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Function: Get exchange rate for currency and date
CREATE OR REPLACE FUNCTION get_exchange_rate(
    p_currency VARCHAR(3),
    p_date DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    currency_code VARCHAR(3),
    usd_rate DECIMAL(12,4),
    khr_rate DECIMAL(12,4)
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        er.currency_code,
        er.usd_rate,
        er.khr_rate
    FROM exchange_rates er
    WHERE er.currency_code = p_currency
      AND er.effective_date <= p_date
    ORDER BY er.effective_date DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;

-- ================================================================
-- TRIGGERS
-- ================================================================

-- Trigger function: Update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to all tables with updated_at
CREATE TRIGGER update_hs_codes_updated_at BEFORE UPDATE ON hs_codes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_duty_rates_updated_at BEFORE UPDATE ON duty_rates
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_fees_updated_at BEFORE UPDATE ON fees
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_exemptions_updated_at BEFORE UPDATE ON exemptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_formulas_updated_at BEFORE UPDATE ON formulas
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_policies_updated_at BEFORE UPDATE ON policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ================================================================
-- GRANTS (Optional - uncomment if using specific roles)
-- ================================================================
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO calculator_readonly;
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO calculator_app;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO calculator_admin;

-- ================================================================
-- END OF SCHEMA
-- ================================================================
