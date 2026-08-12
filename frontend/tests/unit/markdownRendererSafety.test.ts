import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

import { useMarkdown } from '../../app/composables/renderers/useMarkdownRenderer';

const { render } = useMarkdown();

test('markdown renderer supports common markdown features and Khmer text', () => {
  const html = render(`
# Heading

Paragraph with **bold text**, \`inline code\`, and Khmer text: ការនាំចូលទំនិញ។

- Bullet one
- Bullet two

1. Number one
2. Number two

\`\`\`ts
const answer = 'safe';
\`\`\`

[GDCE](https://customs.gov.kh)

| Code | Description |
| --- | --- |
| 1021 | Conditions |
`);

  assert.match(html, /<h1/);
  assert.match(html, /<p class="md-paragraph">/);
  assert.match(html, /<strong>bold text<\/strong>/);
  assert.match(html, /<code class="md-inline-code">inline code<\/code>/);
  assert.match(html, /<ul class="md-list/);
  assert.match(html, /<ol class="md-list/);
  assert.match(html, /markdown-code-fence/);
  assert.match(html, /href="https:\/\/customs.gov.kh"/);
  assert.match(html, /custom-markdown-table-placeholder/);
  assert.match(html, /ការនាំចូលទំនិញ/);
});

test('markdown renderer keeps mermaid and chart placeholder support', () => {
  const mermaidHtml = render(`
\`\`\`mermaid
flowchart TD
  A --> B
\`\`\`
`);
  const chartHtml = render(`
\`\`\`json
{"chartType":"bar","data":[{"label":"A","value":1}]}
\`\`\`
`);

  assert.match(mermaidHtml, /mermaid-diagram-wrap/);
  assert.match(mermaidHtml, /<pre class="mermaid">/);
  assert.match(chartHtml, /custom-markdown-chart-placeholder|markdown-code-fence/);
});

test('markdown renderer sanitization is active and blocks unsafe html', () => {
  const rendererSource = readFileSync('app/composables/renderers/useMarkdownRenderer.ts', 'utf8');
  assert.match(rendererSource, /DOMPurify\.sanitize\(raw,\s*MARKDOWN_PURIFY_CONFIG\)/);

  const html = render(`
<script>window.__unsafe = true</script>
<img src="x" onclick="window.__unsafe = true">
<div onclick="window.__unsafe = true">unsafe html</div>
[bad](javascript:alert(1))
[good](https://example.test)
`);

  assert.doesNotMatch(html, /<script/i);
  assert.doesNotMatch(html, /<[^>]+\sonclick=/i);
  assert.doesNotMatch(html, /href="javascript:/i);
  assert.match(html, /&lt;script&gt;window.__unsafe = true&lt;\/script&gt;/);
  assert.match(html, /&lt;img/);
  assert.match(html, /href="https:\/\/example.test"/);
});

test('markdown renderer handles long answers without dropping content', () => {
  const longWord = 'ក'.repeat(500) + 'A'.repeat(500);
  const html = render(`# Long Answer\n\n${longWord}\n\n${'Long paragraph. '.repeat(200)}`);

  assert.match(html, /Long Answer/);
  assert.match(html, new RegExp(`${'ក'.repeat(20)}`));
  assert.match(html, /Long paragraph/);
});
