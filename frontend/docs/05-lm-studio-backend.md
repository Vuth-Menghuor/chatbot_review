# LM Studio & Backend Setup

## Current setup

LM Studio runs locally (default `http://localhost:1234`). Nuxt proxies via:

```
Browser → /api/lmstudio/* → server/api/lmstudio/[...path].ts → LM Studio
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NUXT_PUBLIC_LM_STUDIO_ENABLED` | — | Enable LM Studio client |
| `NUXT_PUBLIC_LM_STUDIO_BASE_URL` | — | Public base (rewritten to proxy for localhost) |
| `NUXT_PUBLIC_LM_STUDIO_MODEL` | — | Model id |
| `NUXT_PUBLIC_LM_STUDIO_API_TOKEN` | — | Bearer token if needed |
| `NUXT_PUBLIC_LM_STUDIO_TRANSPORT` | `openai_chat` | `openai_chat` \| `native` |
| `NUXT_PUBLIC_LM_STUDIO_STREAM` | — | SSE streaming on/off |
| `NUXT_PUBLIC_LM_STUDIO_CONTEXT_LENGTH` | — | Context window |
| `NUXT_PUBLIC_LM_STUDIO_MAX_HISTORY_MESSAGES` | — | History cap |
| `NUXT_PUBLIC_LM_STUDIO_MAX_HISTORY_CHARS` | — | Char cap |
| `NUXT_LM_STUDIO_UPSTREAM_URL` | `http://localhost:1234` | Server proxy target |
| `NUXT_PUBLIC_ASYNC_TASK_POLL_ENABLED` | `false` | Remote async task polling |
| `NUXT_PUBLIC_ASYNC_TASK_POLL_URL` | — | Poll endpoint (future) |
| `NUXT_PUBLIC_USE_MOCK_API` | — | Use fixture JSON (recommended for UI dev) |

## Transports

### `openai_chat` (default)

- Endpoint: `POST /v1/chat/completions`
- SSE token streaming for markdown/chat tools
- Post-stream: adapter may convert to `UnifiedToolResponse` marker text

### `native`

- Endpoint: `POST /api/v1/chat`
- Single JSON response (no token streaming)
- Full envelope at once

## Teaching vs production

| Mode | Backend | Response format |
|------|---------|-----------------|
| Teaching | LM Studio + short system hint | Model emits JSON envelope or markers |
| Dev UI | Mock fixtures | Valid `UnifiedToolResponse` files |
| Production | Your REST API | Always `UnifiedToolResponse` |

**Do not** rely on a giant system prompt listing every tool JSON schema. The API contract is the source of truth.

## Recommended mock workflow

1. Create `app/mocks/unifiedResponses/demo-hs-report.json` (copy from `docs/02-unified-api-contract.md`).
2. Set `NUXT_PUBLIC_USE_MOCK_API=true`.
3. Short-circuit `useChatStreaming` to load fixture instead of LM Studio.
4. Develop renderers without a running model.

## Async task polling

When `type: report | chart | image` and `mode: async`:

1. UI shows pending state from `taskId`.
2. If `NUXT_PUBLIC_ASYNC_TASK_POLL_ENABLED=true`, poll your API.
3. On completion, `mergePollTaskBlocks` updates the message in place.
4. For LM Studio demo only: `local-chart:*` ids use client-side defer (env-gated).

## Future real API

Your backend should:

1. Return `UnifiedToolResponse` (same schema as docs).
2. Support `POST /chat` with `mode: stream` (SSE chunks as partial envelopes or text).
3. Support `GET /tasks/:taskId` for async tool completion.
4. Accept continuation payloads from ask-back UI (`requestId`, `toolName`, `values`).

## Files

```
server/api/lmstudio/[...path].ts
app/services/chat-api/chatApiHttp.ts
app/services/chat-api/chatApiOpenAi.ts
app/services/chat-api/chatApiClient.ts
app/services/chat-api/chatApiAdapter.ts
app/composables/chat/useChatStreaming.ts
app/composables/chat/useAsyncToolTaskPoll.ts
```
