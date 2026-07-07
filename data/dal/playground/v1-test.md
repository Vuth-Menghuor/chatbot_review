### From d:\dev\data-explorer-project\dal

#### 1. Start everything (builds app, starts Postgres x2 + Redis, runs migrations + seeds)
`docker compose up -d --build`

#### 2. Check logs to see the startup
`docker compose logs -f app`

#### 3. Open Swagger docs
`http://localhost:8000/docs`

#### 4. Try a query
`curl -H "x-api-key: dal-pub-key-abc123xyz789" "http://localhost:8000/v1/query/trade_volume?dimensions=FREQ,PARTNER_COUNTRY,FLOW&measures=VALUE_USD,NETWEIGHT&frequency=M&period_from=2025-Q1&period_to=2026-Q2&limit=10"`
