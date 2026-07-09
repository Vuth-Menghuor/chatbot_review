# Interactive Ask-Back UI

Schema-driven UI for tools that need user input before continuing.

## Use cases

- Confirm HS code classification
- Choose between prediction alternatives
- Fill missing form fields
- Upload additional document
- Approve workflow step

## Proposed tool shape

```json
{
  "toolName": "User Input",
  "type": "structured",
  "mode": "sync",
  "status": "pending",
  "data": {
    "interaction": {
      "kind": "form",
      "title": "Confirm HS code",
      "description": "Please verify the predicted classification.",
      "fields": [
        {
          "name": "hsCode",
          "label": "HS Code",
          "type": "text",
          "default": "1001",
          "required": true
        },
        {
          "name": "confirmed",
          "type": "checkbox",
          "label": "I confirm this classification"
        }
      ],
      "actions": [
        { "id": "submit", "label": "Submit", "primary": true },
        { "id": "cancel", "label": "Cancel" }
      ]
    }
  }
}
```

### `kind` values

| kind | UI |
|------|-----|
| `form` | Vuetify form fields |
| `confirm` | Yes/No dialog inline |
| `select` | Radio or select chips |
| `upload` | File input (reuse ChatInput patterns) |

## Block type

- Canonical: `interaction` (planned — not yet in registry)
- Until added: can use `structured` with `data.interaction` and a new `InteractionRenderer.vue`

## User flow

```
Assistant message with interaction block (status: pending)
    ↓
User fills form → clicks Submit
    ↓
useChat().sendUserReply({ requestId, toolName, action: 'submit', values })
    ↓
API called with meta.continuation
    ↓
Assistant continues with updated tools[]
```

## Continuation request (API)

```json
{
  "message": "Confirmed",
  "meta": {
    "continuation": {
      "requestId": "uuid-12345",
      "toolName": "User Input",
      "action": "submit",
      "values": { "hsCode": "1001", "confirmed": true }
    }
  }
}
```

## Implementation checklist

- [ ] Add `interaction` to `CANONICAL_BLOCK_TYPES`
- [ ] Create `InteractionRenderer.vue` (Vuetify fields from schema)
- [ ] Add `sendUserReply()` to `useChat()`
- [ ] Map `structured` + `data.interaction` in `unifiedToolResponse.ts`
- [ ] i18n for default button labels
- [ ] Disable submit until required fields valid
- [ ] On cancel: mark block `cancelled`, optional user message

## Agent prompt

See [renderers/interaction.md](./renderers/interaction.md).
