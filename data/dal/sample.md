PUBLIC API KEY: `dal-pub-key-abc123xyz789`

DATASET CODE: `trade_volume`
DEFAULT VERSION: `1.0`
ACCESSIBILITY: PUBLIC

METADATA DATASET LIST: `http://localhost:8000/v1/metadata/datasets`
METADATA DATASET DETAILS: `http://localhost:8000/v1/metadata/dataset/trade_volume`

SAMPLE DATA ACCESS: `http://localhost:8000/v1/query/trade_volume?dimensions=PARTNER_COUNTRY,FLOW&measures=VALUE_USD,NETWEIGHT&start-period=2025-Q1&end-period=2026-Q2&limit=1000&frequency=M&filter=FLOW:eq:IM&filter=PARTNER_COUNTRY:eq:US`

HEADER PARAMS: `{x-api-key: 'dal-pub-key-abc123xyz789'}`