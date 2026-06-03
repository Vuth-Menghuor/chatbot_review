-- ================================================================
-- SEED: Dynamic Rules — Current Hardcoded Values
-- ================================================================
-- Seeds the formulas, rounding_rules, policies, and exemptions
-- tables with existing hardcoded values.
-- This ensures zero functional change while making everything editable.
-- Date: 2026-05-04
-- ================================================================

-- ================================================================
-- 1. FORMULAS (from formula_registry.json + formulas.py)
-- ================================================================

INSERT INTO formulas (formula_id, formula_name, formula_type, expression, description, variables, version, effective_date, is_active)
VALUES
    -- Core (Other Products) formulas
    ('CC_001', 'Currency Conversion', 'currency_conversion',
     'cif_value * exchange_rate',
     'Convert CIF value from external currency to KHR using official MEF rate',
     '["cif_value", "exchange_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('COP_001', 'Customs duty on Other Products (COP)', 'cop_amount',
     'customs_value * duty_rate',
     'COP = Customs duty on Other Products. Formula: Customs Value x cd_rate',
     '["customs_value", "duty_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('SOP_001', 'Special tax on Other Products (SOP)', 'sop_amount',
     '(customs_value + cop_amount) * special_tax_rate',
     'SOP = Special tax on Other Products. Base = Customs Value + COP Amount',
     '["customs_value", "cop_amount", "special_tax_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('VOP_001', 'VAT on Other Products (VOP)', 'vop_amount',
     '(customs_value + cop_amount + sop_amount) * vat_rate if sop_amount > 0 else (customs_value + cop_amount) * vat_rate',
     'VOP = VAT on Other Products. Base includes SOP if SOP > 0, otherwise base = Customs Value + COP',
     '["customs_value", "cop_amount", "sop_amount", "vat_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('TDT_001', 'Total Duties and Taxes', 'total_duties_and_taxes',
     'cop_amount + sop_amount + vop_amount',
     'Sum of COP + SOP + VOP',
     '["cop_amount", "sop_amount", "vop_amount"]'::jsonb, 1, '2026-01-01', TRUE),

    ('TP_001', 'Total Payable', 'total_payable',
     'total_duties_and_taxes + processing_fee + inspection_fee + other_fees',
     'Final amount payable including all duties, taxes, and fees',
     '["total_duties_and_taxes", "processing_fee", "inspection_fee", "other_fees"]'::jsonb, 1, '2026-01-01', TRUE),

    -- Petroleum Product formulas
    ('CPP_BASE', 'CPP Base (Declared Value basis)', 'petroleum_cpp_base',
     '(dv_per_ton * exchange_rate * net_mass_kg) / 1000',
     'Petroleum Phase 1: CPP base = (DV per ton x exchange_rate x net_mass_kg) / 1000. DV = fair market price per metric ton.',
     '["dv_per_ton", "exchange_rate", "net_mass_kg"]'::jsonb, 1, '2026-01-01', TRUE),

    ('CPP_001', 'Customs duty on Petroleum Product (CPP)', 'petroleum_cpp',
     'cpp_base * cpp_rate',
     'CPP = Customs duty on Petroleum Product. Formula: CPP base x cd_rate',
     '["cpp_base", "cpp_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('ATP_001', 'Additional Tax on Petroleum product (ATP)', 'petroleum_atp',
     'volume_liter * atp_rate * exchange_rate',
     'ATP = Additional Tax on Petroleum product. ATP base = LTR (Liter). Formula: ATP base x st_rate x exchange_rate = ATP Amount.',
     '["volume_liter", "atp_rate", "exchange_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('SPP_001', 'Special tax on Petroleum Product (SPP)', 'petroleum_spp',
     '(cpp_base + cpp_amount + atp_amount) * spp_rate',
     'SPP = Special tax on Petroleum Product. SPP base = CPP base + CPP amount + ATP amount',
     '["cpp_base", "cpp_amount", "atp_amount", "spp_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('VPP_001', 'VAT on Petroleum Product (VPP)', 'petroleum_vpp',
     '(cpp_base + cpp_amount + atp_amount + spp_amount) * vat_rate',
     'VPP = VAT on Petroleum Product. VPP base = CPP base + CPP + ATP + SPP (NOT spp_base + spp_amount)',
     '["cpp_base", "cpp_amount", "atp_amount", "spp_amount", "vat_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    ('DPP_001', 'Partial subsidy by the state (DPP)', 'petroleum_dpp',
     'phase1_total - phase2_total',
     'DPP = Partial subsidy by the state. DPP = Phase 1 Total (DV basis) - Phase 2 Total (actual CIF basis). Informational only.',
     '["phase1_total", "phase2_total"]'::jsonb, 1, '2026-01-01', TRUE),

    -- DQ formula
    ('DQ_001', 'DQ Adjustment', 'dq_adjustment',
     'amount * dq_factor',
     'DQ = Deal/Trade Agreement between one company and the Cambodia Customs government. Cambodia Customs-specific — not a standard international term. Applied as a multiplier on SOP/SPP.',
     '["amount", "dq_factor"]'::jsonb, 1, '2026-01-01', TRUE),

    -- Rubber export formula
    ('ETR_001', 'Export Tax on Rubber (ETR)', 'rubber_etr',
     '(dv_total_khr / net_mass_kg) * et_rate',
     'ETR = Export Tax on Rubber. Per-kg rate applied to DV total in KHR. VAT does NOT apply on rubber exports.',
     '["dv_total_khr", "net_mass_kg", "et_rate"]'::jsonb, 1, '2026-01-01', TRUE),

    -- FTA/DV formula
    ('FTA_COP', 'FTA Customs duty on Other Products (COP)', 'fta_cop',
     'customs_value * cd_rate',
     'FTA COP: same formula as normal COP but uses the preferential cd_rate from the DB. Rate may be 0% or reduced — never hardcoded to zero.',
     '["customs_value", "cd_rate"]'::jsonb, 1, '2026-01-01', TRUE)

ON CONFLICT (formula_id) DO NOTHING;


-- ================================================================
-- 2. ROUNDING RULES (from rounding_rules.json)
-- ================================================================

INSERT INTO rounding_rules (rule_id, rule_name, applies_to, rounding_method, precision, priority, description, is_active)
VALUES
    ('RULE_001', 'Exchange Rate Precision',
     ARRAY['exchange_rate'], 'NONE', 1, 'CRITICAL',
     'Exchange rates used exactly as published by MEF', TRUE),

    ('RULE_002', 'Currency Conversion Result',
     ARRAY['cif_value_khr'], 'ROUND_WHOLE', 1, 'HIGH',
     'Standard rounding to whole number after currency conversion', TRUE),

    ('RULE_003', 'Tax Components Rounding',
     ARRAY['cop_amount', 'sop_amount', 'vop_amount', 'total_duties_and_taxes'],
     'CEILING_100', 100, 'HIGH',
     'Round UP to nearest 100 after each tax component calculation', TRUE),

    ('RULE_004', 'Final Payment Amount',
     ARRAY['total_payable'], 'CEILING_100', 100, 'CRITICAL',
     'Final payment always rounded UP to nearest 100 (SAD Box B)', TRUE),

    ('RULE_005', 'Quantity Values',
     ARRAY['quantity', 'net_mass_kg', 'gross_mass_kg', 'volume_ltr'],
     'NONE', 1, 'CRITICAL',
     'Quantities use exact declared values — no rounding', TRUE),

    ('RULE_006', 'Tax and Duty Rates',
     ARRAY['duty_rate', 'vat_rate', 'excise_rate', 'special_tax_rate'],
     'NONE', 1, 'CRITICAL',
     'Rates used exactly as published in tariff schedule', TRUE)

ON CONFLICT (rule_id) DO NOTHING;


-- ================================================================
-- 3. POLICIES (DV, DQ, VAT, and business rules)
-- ================================================================

INSERT INTO policies (policy_id, policy_name, policy_type, conditions, actions, priority, description, is_active)
VALUES
    -- VAT rate policy
    ('POL_VAT_STANDARD', 'Standard VAT Rate', 'vat',
     '{}'::jsonb,
     '{"set_rate": {"vat_rate": 0.10}}'::jsonb,
     100, 'Standard VAT rate 10% per Law on Taxation 2023', TRUE),

    -- DV policy
    ('POL_DV_IMPORT', 'DV Import Valuation', 'dv',
     '{"regime": "import"}'::jsonb,
     '{"use_valuation": "fair_market_value"}'::jsonb,
     100, 'DV (Declared Value) is the fair amount of price used to keep the market in the middle, not too high or too low, for imports only', TRUE),

    -- DQ policy
    ('POL_DQ_APPLY', 'DQ Adjustment Rule', 'dq',
     '{"flag_set": "dq_applicable"}'::jsonb,
     '{"apply_formula": "DQ_001", "adjust_base": "sop_amount"}'::jsonb,
     100, 'Apply user-provided DQ factor when dq_applicable is true. No backend registry — user must supply the factor directly.', TRUE),

    -- Petroleum detection
    ('POL_PETROLEUM', 'Petroleum Case Detection', 'duty',
     '{"hs_code_starts_with": "2710"}'::jsonb,
     '{"set_flag": {"petroleum_case": true}}'::jsonb,
     50, 'Auto-detect petroleum case from HS code prefix', TRUE),

    -- Rubber detection
    ('POL_RUBBER', 'Rubber Case Detection', 'duty',
     '{"hs_code_starts_with": "4001"}'::jsonb,
     '{"set_flag": {"rubber_case": true}}'::jsonb,
     50, 'Auto-detect rubber case from HS code prefix', TRUE),

    -- VOP conditional base policy
    ('POL_VOP_BASE', 'VOP Base Determination', 'vat',
     '{}'::jsonb,
     '{"conditional_base": {"if_sop_zero": "customs_value + cop_amount", "if_sop_positive": "customs_value + cop_amount + sop_amount"}}'::jsonb,
     90, 'VOP base is conditional: non-taxable excludes SOP, taxable includes SOP', TRUE)

ON CONFLICT (policy_id) DO NOTHING;


-- ================================================================
-- 4. EXEMPTIONS
-- ================================================================

INSERT INTO exemptions (exemption_code, regime_name, exemption_type, cd_exempt, st_exempt, vat_exempt, et_exempt, cd_reduction_pct, vat_reduction_pct, conditions, is_active)
VALUES
    ('DIP', 'Diplomatic Exemption', 'full',
     TRUE, TRUE, TRUE, TRUE, 100, 100,
     'Valid diplomatic credentials and authorized category required', TRUE),

    ('QIP', 'Qualified Investment Project', 'partial_cd',
     TRUE, FALSE, FALSE, FALSE, 100, 0,
     'Valid QIP certificate from CDC required', TRUE),

    ('NGO', 'Non-Governmental Organization', 'partial_cd',
     TRUE, FALSE, TRUE, FALSE, 100, 100,
     'Valid NGO registration and authorized import list', TRUE),

    ('GOV', 'Government Import', 'full',
     TRUE, TRUE, TRUE, TRUE, 100, 100,
     'Government procurement documentation required', TRUE),

    ('DEV', 'Development Project', 'partial_cd',
     TRUE, FALSE, FALSE, FALSE, 100, 0,
     'Project authorization from relevant ministry', TRUE)

ON CONFLICT (exemption_code) DO NOTHING;


-- ================================================================
-- END OF SEED
-- ================================================================

-- ================================================================
-- FORMULA CORRECTIONS (run after initial seed to patch live data)
-- ================================================================
-- These UPDATE statements fix formulas that were previously seeded
-- with incorrect logic. Safe to re-run; idempotent.

-- Fix FTA_COP: was hardcoded to "customs_value * 0"
-- Now uses actual preferential cd_rate from duty_rates table
UPDATE formulas
SET
    formula_name = 'FTA Customs of Payment',
    expression   = 'customs_value * cd_rate',
    description  = 'FTA: COP uses the actual preferential cd_rate from the DB. Rate may be 0% or reduced — never hardcoded to zero.',
    variables    = '[\"customs_value\", \"cd_rate\"]'::jsonb
WHERE formula_id = 'FTA_COP';

-- Ensure ETR_001 description explicitly blocks VAT (belt-and-suspenders)
UPDATE formulas
SET description = 'Rubber export: ETR per-kg rate. VAT does NOT apply on rubber exports.'
WHERE formula_id = 'ETR_001';
