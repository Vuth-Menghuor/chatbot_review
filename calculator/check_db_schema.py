"""Check the actual exchange_rates table schema in PostgreSQL."""

import os
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    database="gdce_calculator_local",
    user="postgres",
    password="16112005",
)
cur = conn.cursor()

# Get column names
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'exchange_rates'
    ORDER BY ordinal_position;
""")
columns = cur.fetchall()
print("exchange_rates columns:")
for col, dtype in columns:
    print(f"  {col}: {dtype}")

# Check constraints / indexes
cur.execute("""
    SELECT tc.constraint_name, tc.constraint_type, kcu.column_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
        AND tc.table_name = kcu.table_name
    WHERE tc.table_name = 'exchange_rates';
""")
constraints = cur.fetchall()
print("\nConstraints:")
for c in constraints:
    print(f"  {c}")

cur.close()
conn.close()
