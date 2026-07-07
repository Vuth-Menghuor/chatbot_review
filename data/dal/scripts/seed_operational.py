"""
Seed operational database with server-matching schema and tables for local development.

Creates schemas: metadata, aggregate_data
Creates tables:
- metadata.countries
- metadata.mot_border
- public.hs2_codes
- public.hs4_codes
- metadata.classification_correlation
- metadata.sitc
- metadata.uom_stats
- aggregate_data.trade_data

Run: python -m scripts.seed_operational
"""

from __future__ import annotations

import asyncio
from sqlalchemy import text
from app.db.operational_session import get_operational_session_factory

SCHEMA_SQL = """
CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA IF NOT EXISTS aggregate_data;

-- Reference table: countries
CREATE TABLE IF NOT EXISTS metadata.countries (
    code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    valid_to TIMESTAMP
);

-- Reference table: mode of transport
CREATE TABLE IF NOT EXISTS metadata.mot_border (
    code VARCHAR(10) PRIMARY KEY,
    desc_en VARCHAR(200) NOT NULL,
    valid_to TIMESTAMP
);

-- Reference table: HS2 codes
CREATE TABLE IF NOT EXISTS public.hs2_codes (
    hs2_cod VARCHAR(10) PRIMARY KEY,
    hs2_dsc VARCHAR(200) NOT NULL,
    valid_to TIMESTAMP
);

-- Reference table: HS4 codes
CREATE TABLE IF NOT EXISTS public.hs4_codes (
    hs4_cod VARCHAR(10) PRIMARY KEY,
    hs4_dsc VARCHAR(200) NOT NULL,
    valid_to TIMESTAMP
);

-- Reference table: classification correlation
CREATE TABLE IF NOT EXISTS metadata.classification_correlation (
    hs8_code VARCHAR(20) NOT NULL,
    hs_version VARCHAR(10) NOT NULL,
    sitc_version VARCHAR(10) NOT NULL,
    sitc_code VARCHAR(20) NOT NULL,
    valid_to TIMESTAMP,
    PRIMARY KEY (hs8_code, hs_version, sitc_version)
);

-- Reference table: SITC
CREATE TABLE IF NOT EXISTS metadata.sitc (
    code VARCHAR(20) NOT NULL,
    desc_en VARCHAR(200) NOT NULL,
    digit INTEGER NOT NULL,
    revision VARCHAR(10) NOT NULL,
    valid_to TIMESTAMP,
    PRIMARY KEY (code, digit, revision)
);

-- Reference table: units of measure stats
CREATE TABLE IF NOT EXISTS metadata.uom_stats (
    code VARCHAR(10) PRIMARY KEY,
    desc_en VARCHAR(200) NOT NULL,
    valid_to TIMESTAMP
);

-- Main fact table: trade data in aggregate_data schema
CREATE TABLE IF NOT EXISTS aggregate_data.trade_data (
    id SERIAL PRIMARY KEY,
    ref_year INTEGER NOT NULL,
    ref_month INTEGER NOT NULL,
    partner_country VARCHAR(10) NOT NULL REFERENCES metadata.countries(code),
    mot_border VARCHAR(10) NOT NULL REFERENCES metadata.mot_border(code),
    flow VARCHAR(20) NOT NULL,
    hs2_code VARCHAR(10) REFERENCES public.hs2_codes(hs2_cod),
    hs4_code VARCHAR(10) REFERENCES public.hs4_codes(hs4_cod),
    hs8_code VARCHAR(20),
    value_usd NUMERIC(18,2),
    value_khr NUMERIC(18,2),
    net_weight NUMERIC(18,2),
    quantity NUMERIC(18,2),
    unit_code VARCHAR(10) REFERENCES metadata.uom_stats(code)
);

CREATE INDEX IF NOT EXISTS ix_trade_data_year_month ON aggregate_data.trade_data(ref_year, ref_month);
CREATE INDEX IF NOT EXISTS ix_trade_data_partner ON aggregate_data.trade_data(partner_country);
CREATE INDEX IF NOT EXISTS ix_trade_data_flow ON aggregate_data.trade_data(flow);
"""

SEED_SQL = """
-- Countries
INSERT INTO metadata.countries (code, name, valid_to) VALUES
    ('US', 'United States', NULL),
    ('CN', 'China', NULL),
    ('JP', 'Japan', NULL),
    ('DE', 'Germany', NULL),
    ('GB', 'United Kingdom', NULL),
    ('KR', 'South Korea', NULL),
    ('SG', 'Singapore', NULL),
    ('TH', 'Thailand', NULL),
    ('VN', 'Viet Nam', NULL),
    ('UY', 'Uruguay', NULL)
ON CONFLICT (code) DO NOTHING;

-- Mode of transport
INSERT INTO metadata.mot_border (code, desc_en, valid_to) VALUES
    ('1', 'Sea transport', NULL),
    ('2', 'Rail transport', NULL),
    ('3', 'Road transport', NULL),
    ('4', 'Air transport', NULL),
    ('5', 'Inland waterways transport', NULL),
    ('9', 'Other', NULL)
ON CONFLICT (code) DO NOTHING;

-- HS2 codes
INSERT INTO public.hs2_codes (hs2_cod, hs2_dsc, valid_to) VALUES
    ('61', 'Articles of apparel and clothing accessories, knitted or crocheted.', NULL),
    ('62', 'Articles of apparel and clothing accessories, not knitted or crocheted.', NULL)
ON CONFLICT (hs2_cod) DO NOTHING;

-- HS4 codes
INSERT INTO public.hs4_codes (hs4_cod, hs4_dsc, valid_to) VALUES
    ('6203', 'Men''s or boys'' suits, ensembles, jackets, blazers, trousers, bib and brace overalls, breeches and shorts (other than swimwear).', NULL),
    ('6204', 'Women''s or girls'' suits, ensembles, jackets, blazers, dresses, skirts, divided skirts, trousers, bib and brace overalls, breeches and shorts (other than swimwear).', NULL),
    ('6205', 'Men''s or boys'' shirts.', NULL),
    ('6207', 'Men''s or boys'' singlets and other vests, underpants, briefs, nightshirts, pyjamas, bathrobes, dressing gowns and similar articles.', NULL),
    ('6211', 'Track suits, ski suits and swimwear, other garments.', NULL),
    ('6217', 'Other made up clothing accessories, parts of garments or of clothing accessories, other than those of heading 62.12.', NULL)
ON CONFLICT (hs4_cod) DO NOTHING;

-- Classification correlation
INSERT INTO metadata.classification_correlation (hs8_code, hs_version, sitc_version, sitc_code, valid_to) VALUES
    ('62030000', '2022', 'rev4', '841', NULL),
    ('62040000', '2022', 'rev4', '842', NULL),
    ('62050000', '2022', 'rev4', '841', NULL),
    ('62070000', '2022', 'rev4', '841', NULL),
    ('62110000', '2022', 'rev4', '842', NULL),
    ('62170000', '2022', 'rev4', '842', NULL)
ON CONFLICT DO NOTHING;

-- SITC
INSERT INTO metadata.sitc (code, desc_en, digit, revision, valid_to) VALUES
    ('8', 'Miscellaneous manufactured articles', 1, 'rev4', NULL),
    ('84', 'Articles of apparel and clothing accessories', 2, 'rev4', NULL)
ON CONFLICT DO NOTHING;

-- Units of measure
INSERT INTO metadata.uom_stats (code, desc_en, valid_to) VALUES
    ('KGM', 'Weight in kilograms', NULL),
    ('LTR', 'Volume in liters', NULL),
    ('NAR', 'Number of articles', NULL)
ON CONFLICT (code) DO NOTHING;

-- Fact trade data
INSERT INTO aggregate_data.trade_data (ref_year, ref_month, partner_country, mot_border, flow, hs2_code, hs4_code, hs8_code, value_usd, value_khr, net_weight, quantity, unit_code) VALUES
    (2025, 1, 'US', '1', 'IMPORT', '62', '6203', '62030000', 1200000.00, 4800000000.00, 65000.00, 500.00, 'KGM'),
    (2025, 1, 'US', '4', 'EXPORT', '62', '6205', '62050000', 850000.00, 3400000000.00, 12000.00, 200.00, 'KGM'),
    (2025, 1, 'CN', '1', 'IMPORT', '61', '6217', '62170000', 2500000.00, 10000000000.00, 180000.00, NULL, 'KGM'),
    (2026, 1, 'UY', '5', 'EXPORT', '62', '6211', '62110000', 1087.50, 4350000.00, 91.05, 91.05, 'KGM'),
    (2026, 1, 'UY', '5', 'EXPORT', '62', '6204', '62040000', 540.00, 2160000.00, 116.00, 120.00, 'NAR'),
    (2026, 1, 'VN', '5', 'EXPORT', '62', '6203', '62030000', 931446.25, 3725785000.00, 41864.44, 83358.00, 'NAR')
ON CONFLICT DO NOTHING;
"""

async def seed():
    """Create schemas, tables, and insert sample operational data."""
    factory = get_operational_session_factory()
    async with factory() as session:
        # Create tables
        for stmt in SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()

        # Seed data
        for stmt in SEED_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()

    print("=" * 60)
    print("Operational database seeded with server-matching structure successfully!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(seed())
