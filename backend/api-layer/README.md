# Chatbot API Layer

FastAPI gateway for the chatbot frontend. It owns identity, access control,
projects, chat sidebar metadata, rate limits, and logs. It does not generate
answers or store full conversation content.

## Architecture

Normal text takes the low-latency path:

```text
Main Chatbot Service token stream -> API Layer SSE proxy -> frontend fetch stream
```

Long work stays in the Main Chatbot Service infrastructure:

```text
Main Chatbot Service -> RabbitMQ -> worker -> MinIO/S3 -> job result URL
```

The API Layer only proxies job status and result endpoints. It neither publishes
RabbitMQ jobs nor uploads generated artifacts.

## Data ownership

The API Layer PostgreSQL database stores users, password hashes, refresh-token
hashes, API-key hashes, projects, chat-thread metadata, request logs, and audit
logs. Redis stores short-lived rate counters and the access-token blacklist.

The Main Chatbot Service owns full messages, conversation context, routing and
service responses, feedback content, async job metadata, and result URLs.
Workers store binary results in MinIO/S3. The API Layer never stores full
messages, chatbot context, generated files, raw refresh tokens, or raw API keys.

## Setup

Requirements: Python 3.12+, PostgreSQL 16+, and Redis 7+.

```bash
cd backend/api-layer
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for OpenAPI documentation.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Async SQLAlchemy PostgreSQL URL |
| `REDIS_URL` | Redis connection URL |
| `MAIN_CHATBOT_SERVICE_URL` | Internal Main Chatbot Service base URL |
| `JWT_SECRET_KEY` | JWT signing secret; replace in every deployment |
| `JWT_ALGORITHM` | Signing algorithm, normally `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token lifetime |
| `FRONTEND_ORIGINS` | Comma-separated CORS allowlist |
| `HTTP_TIMEOUT_SECONDS` | Non-streaming upstream timeout |

## Docker

The compose file expects an external network shared with the existing Main
Chatbot Service. Create it once (or set `CHATBOT_DOCKER_NETWORK` to an existing
network), then start the three API Layer containers:

```bash
docker network create chatbot-shared
cp .env.example .env
docker compose up --build -d
docker compose logs -f api-layer
```

### Full development stack with Orchestrator v2

The workspace's orchestrator exposes a development-only compatibility API at
`/internal/*`. It uses the existing coordinator, emits SSE events, and keeps
chat history in memory. Restarting the orchestrator clears that history.

Start all specialized services, the orchestrator, and the API Layer:

```powershell
backend/api-layer/scripts/start-development.ps1
```

For later starts that should reuse existing images:

```powershell
backend/api-layer/scripts/start-development.ps1 -SkipBuild
```

All services share `gdce-network`. The API Layer reaches
`http://orchestrator-service:8001`; the orchestrator reaches
`general-service:8005`, `retrieval-service:8003`, `calculator:8002`, and
`trade-service:8004`. Run the reusable smoke test separately with:

```powershell
python backend/api-layer/scripts/check_integration.py
```

Development limitations: orchestrator chat history and feedback are in memory.
The calculator can use JSON/Qdrant fallbacks but needs its own populated
PostgreSQL duty-rate database for authoritative calculations. Trade queries need
a valid `DAL_BASE_URL` and `DAL_API_KEY` in the trade service environment.

Compose contains only `api-layer`, `api-postgres`, and `api-redis`. Migrations
run automatically before the API starts.

## Alembic

```bash
alembic upgrade head
alembic current
alembic revision --autogenerate -m "describe change"
alembic downgrade -1
```

## Authentication examples

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"full_name":"Test User","email":"test@example.com","password":"password123"}'

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password123"}'

curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

Protected endpoints accept either `Authorization: Bearer <token>` or
`X-API-Key: <key>`. API keys are returned once at creation.

## Projects and chats

```bash
curl -X POST http://localhost:8000/api/v1/projects \
  -H "Authorization: Bearer ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Customs Calculation","color":"#2563EB","icon":"folder"}'

curl http://localhost:8000/api/v1/chats \
  -H "Authorization: Bearer ACCESS_TOKEN"

curl "http://localhost:8000/api/v1/chats?project_id=null" \
  -H "Authorization: Bearer ACCESS_TOKEN"
```

The gateway verifies that every project and chat belongs to the authenticated
user. Deletes are soft deletes. Deleting a project detaches its active chats.

## Main Chatbot Service contract

The gateway calls these internal endpoints:

- `POST /internal/chat/send`
- `POST /internal/chat/stream`
- `GET /internal/chat/history`
- `POST /internal/chat/feedback`
- `GET|DELETE /internal/chats/{chat_id}...`
- `GET /internal/jobs/{job_id}` and `/result`

Forwarded chat requests include `chat_id`, `project_id`, `user_id`, `role`,
`message`, `attachments`, `metadata`, and `request_id`. The internal service must
authorize the supplied identity at its trust boundary and return SSE-formatted
chunks from its stream endpoint.

## Streaming from the frontend

`EventSource` cannot POST, so use `fetch()` and read `response.body`. The API
returns `text/event-stream`, disables proxy buffering, and relays upstream bytes
without collecting the answer.

```javascript
async function sendMessageStream({ token, chatId, projectId, message }) {
  const response = await fetch("http://localhost:8000/api/v1/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    },
    body: JSON.stringify({ chat_id: chatId, project_id: projectId, message })
  });
  if (!response.ok || !response.body) throw new Error("Streaming failed");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assistantText = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";
    for (const block of events) {
      let type = "message";
      const dataLines = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
      }
      if (!dataLines.length) continue;
      const data = JSON.parse(dataLines.join("\n"));
      if (type === "token") {
        assistantText += data.content;
        renderAssistantMessage(assistantText);
      } else if (type === "job") showJobCard(data);
      else if (type === "done") markMessageDone(data);
      else if (type === "error") showError(data.detail);
    }
  }
}
```

Show the user message immediately, reuse one assistant bubble, batch visual
updates with `requestAnimationFrame`, display a typing cursor, and only
auto-scroll when the user is near the bottom.

## Async jobs

A stream or normal send may return a job descriptor. Poll
`GET /api/v1/jobs/{job_id}` until it reaches `completed` or `failed`, then call
`GET /api/v1/jobs/{job_id}/result`. The result contains MinIO/S3 URLs and file
metadata; the API Layer does not download or persist that artifact.

## Security and operations

- Passwords use bcrypt; refresh tokens and API keys are stored only as SHA-256 hashes.
- Access tokens are short lived and logout blacklists their JWT ID in Redis.
- Login/register, chat, and general API limits use Redis and return HTTP 429.
- CORS origins come only from `FRONTEND_ORIGINS`.
- Request logs exclude bodies, passwords, tokens, and sensitive headers.
- Upstream URLs are never returned to the browser.
- Set a strong `JWT_SECRET_KEY`, use TLS at ingress, rotate secrets, and restrict the shared Docker network in production.

## Tests

```bash
pytest
python -m compileall app alembic
```
