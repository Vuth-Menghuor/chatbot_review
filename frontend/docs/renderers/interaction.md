# Interaction Renderer — Agent Prompt (Planned)

**Block type:** `interaction` (planned)  
**Component:** _not yet created_ — `InteractionRenderer.vue`  
**Spec:** `docs/06-interactive-ask-back.md`

---

## Copy-paste prompt

````
Implement the Interaction (ask-back) renderer in Chat-Bot-GDCE. Schema-driven forms that let the API ask the user questions and continue the conversation. No hardcoded fields.

## Context
- New block type for `structured` tools with `data.interaction`
- Vuetify form fields inside Tailwind chat bubble
- Submit calls `useChat().sendUserReply()`

## Read first
- `docs/06-interactive-ask-back.md`
- `ChatInput.vue` (attachment patterns)
- `StructuredToolData` in types

## Data contract

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
      "description": "Verify the predicted classification.",
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
        },
        {
          "name": "category",
          "type": "select",
          "label": "Category",
          "options": [
            { "value": "agri", "label": "Agriculture" },
            { "value": "mineral", "label": "Minerals" }
          ]
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

### Field types to support
`text`, `textarea`, `number`, `checkbox`, `select`, `radio`, `date`, `file`

### kinds
`form`, `confirm`, `select`, `upload`

## Implementation

1. Add `interaction` to `CANONICAL_BLOCK_TYPES`
2. Create `InteractionRenderer.vue`
3. In `unifiedToolResponse.ts`: if `structured` + `data.interaction` → `interaction` block (not tool_output JSON)
4. Register in `rendererMap`
5. Add `sendUserReply({ requestId, toolName, action, values })` to `useChat()`
6. Pass `meta.continuation` in next API request via `useChatStreaming`

## UX
- Card inside assistant message with title + description
- Vuetify `v-text-field`, `v-checkbox`, `v-select`, `v-file-input`
- Primary submit disabled until required fields valid
- After submit: disable form, show submitted summary chips
- Cancel: mark block cancelled, optional user-visible "Cancelled"

## Rules
- Render fields from schema only — zero hardcoded field names
- i18n default action labels with schema override
- Accessible labels + `aria-invalid` on validation errors
- File upload reuses existing file utils

## Files to create/touch
- `app/components/renderers/InteractionRenderer.vue`
- `app/composables/renderers/useInteractionRenderer.ts`
- `app/composables/index.ts` → `sendUserReply`
- `app/composables/chat/useChatStreaming.ts` → continuation meta
- `unifiedToolResponse.ts` → branch in `structuredToBlocks`
- `useRenderer.ts` → registry

## Acceptance
- [ ] Form renders from interaction schema.
- [ ] Submit sends continuation and disables form.
- [ ] Cancel works without API call or with cancel action.
- [ ] Required validation blocks submit.
- [ ] Works in dark mode + km locale.
````
