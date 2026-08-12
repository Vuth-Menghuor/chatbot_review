#!/usr/bin/env python3
"""
Migration v2: Add origin_country back to preferential_rates
===========================================================
Transforms the simplified preferential_rates table into an
agreement-code + origin-country lookup.

Usage: python migrate_preferential_rates_v2.py
"""

import os
import sys
from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=env_path)

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

DB_CONFIG = {
    "host": os.getenv("CALCULATOR_DB_HOST", "localhost"),
    "port": int(os.getenv("CALCULATOR_DB_PORT", "5432")),
    "database": os.getenv("CALCULATOR_DB_NAME", "gdce_calculator"),
    "user": os.getenv("CALCULATOR_DB_USER", "calc_app"),
    "password": os.getenv("CALCULATOR_DB_PASSWORD", ""),
}

# Agreement codes with their eligible origin countries (from official scopes)
AGREEMENT_COUNTRIES = {
    "AJCEP": ["KH", "TH", "VN", "JP"],
    "CEPT":  ["KH", "TH", "VN", "LA", "SG", "MY", "ID", "PH", "BN", "MM"],
    "ATIGA": ["KH", "TH", "VN", "LA", "SG", "MY", "ID", "PH", "BN", "MM"],
    "AHKCFTA": ["KH", "TH", "VN", "HK"],
    "ACFTA": ["KH", "TH", "VN", "CN"],
    "AJFTA": ["KH", "TH", "VN", "JP"],
    "RCEP":  ["KH", "TH", "VN", "CN", "JP", "KR", "AU", "NZ", "IN"],
    "CCFTA": ["KH", "CN"],
    "CKFTA": ["KH", "KR"],
    "AANZFTA": ["KH", "TH", "VN", "AU", "NZ"],
    "AKFTA": ["KH", "TH", "VN", "KR"],
    "AIFTA": ["KH", "TH", "VN", "IN"],
    "KHUSPT": ["KH", "US"],
}

AGREEMENT_NAMES = {
    "AJCEP": (None, "ASEAN-JAPAN Compr. Eco. Partnership"),
    "CEPT":  (None, "Common Effective Preferent. Tariff"),
    "ATIGA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មទំនិញអាស៊ាន", "ASEAN Trade In Goods Agreement"),
    "AHKCFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន-ហុងកុង", "ASEAN-Hong Kong Free Trade Agreement"),
    "ACFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ចិន", "ASEAN-China Free Trade Agreement"),
    "AJFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ជប៉ុន", "ASEAN-Japan Free Trade Agreement"),
    "RCEP":  ("កិច្ចព្រមព្រៀងភាពជាដៃគូសេដ្ឋកិច្ចគ្រប់ជ្រុងជ្រោយតំបន់ ", "Regional Comprehensive Economic Partnership Agreement"),
    "CCFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី កម្ពុជា-ចិន", "Cambodia-China Free Trade Agreement"),
    "CKFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី កម្ពុជា-កូរ៉េ", "Cambodia-Korea Free Trade Agreement"),
    "AANZFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរីអាស៊ាន -អូស្រ្តាលី -ណូវ៉ែលហ្សេឡង់", "ASEAN-Australia-New Zealand Free Trade Agreement"),
    "AKFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-កូរ៉េ", "ASEAN-Korea Free Trade Agreement"),
    "AIFTA": ("កិច្ចព្រមព្រៀងពាណិជ្ជកម្មសេរី អាស៊ាន-ឥណ្ឌា", "ASEAN-India Free Trade Agreement"),
    "KHUSPT": ("ពន្ធអនុគ្រោះកម្ពុជា-សហរដ្ឋអាម៉េរិក", "KH and US Preferential Tariff"),
}

VALID_FROM = {
    "AJCEP": "2010-01-01", "CEPT": "2000-01-01", "ATIGA": "2015-11-01",
    "AHKCFTA": "2020-11-14", "ACFTA": "2008-09-22", "AJFTA": "2017-04-07",
    "RCEP": "2021-10-04", "CCFTA": "2021-10-05", "CKFTA": "2022-01-29",
    "AANZFTA": "2010-10-29", "AKFTA": "2007-12-08", "AIFTA": "2011-02-09",
    "KHUSPT": "2025-08-08",
}

VALID_TO = {
    "AJCEP": "2017-04-07",
    "CEPT": "2015-11-05",
}


def run_migration():
    print("=" * 60)
    print("Preferential Rates Migration v2 — Add origin_country")
    print("=" * 60)
    print(f"Database: {DB_CONFIG['database']} @ {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    print()

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()

        # Check current columns
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'preferential_rates' ORDER BY ordinal_position
        """)
        columns = [row[0] for row in cur.fetchall()]
        print(f"Current columns: {', '.join(columns)}")

        if 'origin_country' in columns:
            print("Table already has origin_country. Skipping schema change.")
        else:
            print("Adding origin_country column...")
            cur.execute("""
                ALTER TABLE preferential_rates
                ADD COLUMN origin_country TEXT NOT NULL DEFAULT 'XX';
            """)
            cur.execute("""
                ALTER TABLE preferential_rates
                DROP CONSTRAINT IF EXISTS preferential_rates_agreement_code_key;
            """)
            cur.execute("""
                ALTER TABLE preferential_rates
                ADD CONSTRAINT preferential_rates_unique_agreement_country
                UNIQUE (agreement_code, origin_country);
            """)
            print("Schema updated.")

        # Check if seed data already exists
        cur.execute("""
            SELECT COUNT(*) FROM preferential_rates WHERE origin_country != 'XX'
        """)
        existing = cur.fetchone()[0]
        print(f"Existing country-mapped rows: {existing}")

        if existing > 0:
            print("Data already seeded. Skipping seed.")
        else:
            print("Seeding agreement + country mappings...")
            rows = []
            for code, countries in AGREEMENT_COUNTRIES.items():
                name_kh, name_en = AGREEMENT_NAMES[code]
                vf = VALID_FROM[code]
                vt = VALID_TO.get(code)
                for country in countries:
                    rows.append((code, country, name_kh, name_en, vf, vt))

            cur.executemany("""
                INSERT INTO preferential_rates
                (agreement_code, origin_country, name_kh, name_en, valid_from, valid_to)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (agreement_code, origin_country) DO NOTHING
            """, rows)
            print(f"Inserted {len(rows)} rows.")

        # Verify
        cur.execute("""
            SELECT agreement_code, origin_country, name_en
            FROM preferential_rates
            WHERE origin_country != 'XX'
            ORDER BY agreement_code, origin_country
        """)
        rows = cur.fetchall()
        print(f"\nTotal agreement-country pairs: {len(rows)}")
        current_agreement = None
        countries = []
        for code, country, name in rows:
            if code != current_agreement:
                if current_agreement:
                    print(f"  -> {', '.join(countries)}")
                current_agreement = code
                countries = []
                print(f"\n{code}: {name}")
            countries.append(country)
        if current_agreement:
            print(f"  -> {', '.join(countries)}")

        cur.close()
        conn.close()
        print("\nMigration complete!")

    except psycopg2.OperationalError as e:
        print(f"\nDatabase connection failed: {e}")
        print("Check your .env file and ensure PostgreSQL is running.")
        sys.exit(1)
    except Exception as e:
        print(f"\nMigration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_migration()
