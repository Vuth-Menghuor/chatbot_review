# Image Renderer — Agent Prompt

**Block type:** `image`  
**Component:** `app/components/renderers/ImageRenderer.vue`  
**Composable:** `app/composables/renderers/useImageRenderer.ts`

---

## Copy-paste prompt

````
Refactor the Image renderer in Chat-Bot-GDCE (`ImageRenderer.vue`, `useImageRenderer.ts`). Show generated images from async/sync API tools — no placeholder hardcoded URLs.

## Context
- `type: "image"` — AI image generation or attachment display.
- Supports pending/loading, success URL, and error states.

## Data contract

### Async pending
```json
{
  "toolName": "Image Generation",
  "type": "image",
  "mode": "async",
  "status": "pending",
  "taskId": "task-791"
}
```

### Completed
```json
{
  "toolName": "Image Generation",
  "type": "image",
  "mode": "sync",
  "status": "success",
  "data": {
    "prompt": "A golden wheat field at sunset",
    "imageUrl": "https://cdn.example.com/images/task-791.png",
    "title": "Generated image"
  }
}
```

### Content aliases (normalizer)
- URL: `imageUrl` | `url` | `src`
- String content on block → direct URL

### MessageBlock content
```ts
{
  prompt?: string;
  imageUrl?: string;
  loading?: boolean;
  error?: boolean | string;
  status?: 'pending' | 'processing' | 'completed' | 'error';
  title?: string;
}
```

## UX
- Skeleton while `loading` or `status: pending|processing`
- Lazy load image with fade-in on `load`
- Error fallback icon + message
- Show prompt with copy button (composable has `copyText`)
- Regenerate emit: `@regenerate` → parent `useChat().regenerate()`
- Max-width responsive, rounded corners, dark mode border

## Async
- Poll task completion → merge `imageUrl` into block
- `imageToBlocks` sets `loading: true` when `status: pending|processing`

## Rules
- No hardcoded demo images.
- i18n: "Copy prompt", "Generating image...", "Failed to load image"
- Alt text from `title` or `prompt`

## Files
- `ImageRenderer.vue`, `useImageRenderer.ts`
- `unifiedToolResponse.ts` → `imageToBlocks()`
- `useAsyncToolTaskPoll.ts`

## Acceptance
- [ ] Pending shows loading skeleton.
- [ ] imageUrl renders with lazy load.
- [ ] Broken URL shows error state.
- [ ] Copy prompt works.
- [ ] Poll merge updates image in place.
````
