# Calculator Responses

GDCE calculator responses use the normalized chat v1 contract from the API
layer. They do not require a dedicated `CalculatorRenderer`.

## Rendering Contract

Render `message.content` by block type through the normal renderer registry:

- `summary`
- `key_value`
- `table`
- `details`
- `references`
- `markdown` fallback
- `clarification` and `error` when applicable

The frontend must not choose calculator UI by checking `service`, `intent`, HS
code prefix, or product category. Renderer selection is only:

```ts
rendererRegistry[block.type]
```

Unknown block types use the safe fallback renderer.

## Fallback And Copy Text

`message.content` is the visual source of truth. If it has blocks, render those
blocks and do not also render the full `response.content` markdown answer.

`response.content` remains the plain-text fallback for copy, export,
accessibility, and clients that cannot render structured blocks. If
`message.content` is empty, render `response.content` as a markdown block.

## Legacy Formula Tools

Older local tool payloads named `calculator`, `calc`, `math`, `latex`, or
`formula` may still be converted to markdown by the legacy tool pipeline. That
path is separate from the GDCE API-layer calculator response contract.
