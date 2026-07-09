/**
 * Convert LaTeX math delimiters from LLM output into markdown code / inline code.
 * Used instead of MathJax — ChatGPT-style highlighted formulas.
 *
 * Important: currency like `$100 × 1.20 = $120` must NOT be parsed as LaTeX `$...$`
 * or inline backticks break and only part of the formula gets highlighted.
 */

const CODE_SLOT = '\uE000';
const CODE_MARK = '\uE001';

function protectMarkdownCode(content: string): { text: string; slots: string[] } {
  const slots: string[] = [];
  let text = content;

  text = text.replace(/```[\s\S]*?```/g, (match) => {
    const id = slots.length;
    slots.push(match);
    return `${CODE_SLOT}F${id}${CODE_MARK}`;
  });

  text = text.replace(/`[^`\n]+`/g, (match) => {
    const id = slots.length;
    slots.push(match);
    return `${CODE_SLOT}I${id}${CODE_MARK}`;
  });

  return { text, slots };
}

function restoreMarkdownCode(text: string, slots: string[]): string {
  return text.replace(new RegExp(`${CODE_SLOT}[FI](\\d+)${CODE_MARK}`, 'g'), (_m, id) => {
    return slots[Number(id)] ?? '';
  });
}

function stripLatexToPlain(latex: string): string {
  let s = latex.trim();
  if (!s) return '';

  s = s.replace(/\\\$/g, '$');

  let safety = 0;
  while (/\\(?:text|mathrm|mathbf|textbf|textit|textrm)\{/.test(s) && safety++ < 64) {
    s = s.replace(/\\(?:text|mathrm|mathbf|textbf|textit|textrm)\{([^{}]*)\}/g, '$1');
  }

  safety = 0;
  while (s.includes('\\frac') && safety++ < 64) {
    s = s.replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, '($1 / $2)');
  }

  s = s
    .replace(/\\times/g, ' × ')
    .replace(/\\div/g, ' ÷ ')
    .replace(/\\cdot/g, ' · ')
    .replace(/\\%/g, '%')
    .replace(/\\left[([{]?\s*/g, '')
    .replace(/\\right[\])}]?\s*/g, '')
    .replace(/\\(?:approx|sim|simeq)/g, '≈')
    .replace(/\\(?:leq|le)/g, '≤')
    .replace(/\\(?:geq|ge)/g, '≥');

  safety = 0;
  while (/\\[a-zA-Z]+\{/.test(s) && safety++ < 64) {
    s = s.replace(/\\([a-zA-Z]+)\{([^{}]*)\}/g, '$2');
  }

  s = s.replace(/\\([a-zA-Z]+)/g, ' $1 ');
  s = s.replace(/[{}]/g, '');
  s = s.replace(/\s+/g, ' ').trim();

  return s;
}

function blockFence(plain: string, lang = 'text'): string {
  const body = plain.trim();
  if (!body) return '';
  return `\n\`\`\`${lang}\n${body}\n\`\`\`\n`;
}

function inlineCode(plain: string): string {
  const body = plain.trim();
  if (!body) return '';
  return `\`${body.replace(/`/g, '\\`')}\``;
}

/** True when `$...$` is LaTeX — not currency like `$100 ... $120`. */
function isLikelyLatexInline(inner: string): boolean {
  const t = inner.trim();
  if (!t) return false;

  if (/\\[a-zA-Z]/.test(t)) return true;
  if (/[{}^_]/.test(t)) return true;

  // Currency / arithmetic: starts with digit or is mostly numbers with $ amounts
  if (/^\d/.test(t)) return false;
  if (/(?:^|\s)\$\d/.test(t)) return false;
  if (/^\$?\d+([.,]\d+)?(\s*[×x*+\-/]\s*\$?\d+)+/i.test(t)) return false;

  // Variable-style math: E = mc^2
  if (/^[A-Za-z]/.test(t) && /[=+\-*/^]/.test(t)) return true;

  return false;
}

const INLINE_LATEX_RE = /(?<!\$)\$(?!\$)([^\n$]+?)\$(?!\$)/g;
const BLOCK_LATEX_RE = /\$\$([\s\S]*?)\$\$/g;
const DISPLAY_BRACKET_RE = /\\\[([\s\S]*?)\\\]/g;
const INLINE_PAREN_RE = /\\\(([^)]*?)\\\)/g;

/** True when content likely contains LaTeX math delimiters (not plain currency). */
export function hasLatexMathDelimiters(content: string): boolean {
  if (BLOCK_LATEX_RE.test(content)) return true;
  if (DISPLAY_BRACKET_RE.test(content)) return true;
  if (INLINE_PAREN_RE.test(content)) return true;

  INLINE_LATEX_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = INLINE_LATEX_RE.exec(content)) !== null) {
    if (isLikelyLatexInline(match[1] ?? '')) return true;
  }
  return false;
}

function normalizeLatexCore(content: string): string {
  let result = content;

  result = result.replace(BLOCK_LATEX_RE, (_match, math: string) => {
    const plain = stripLatexToPlain(math);
    if (!plain) return '';
    const lang = /^[=+\-*/^]|[A-Z]+\d|=\s*[A-Z]+\d/i.test(plain) ? 'excel' : 'text';
    return blockFence(plain, lang);
  });

  result = result.replace(DISPLAY_BRACKET_RE, (_match, math: string) => {
    const plain = stripLatexToPlain(math);
    return plain ? blockFence(plain, 'text') : '';
  });

  result = result.replace(INLINE_LATEX_RE, (match, math: string) => {
    if (!isLikelyLatexInline(math)) return match;
    const plain = stripLatexToPlain(math);
    return plain ? inlineCode(plain) : match;
  });

  result = result.replace(INLINE_PAREN_RE, (_match, math: string) => {
    const plain = stripLatexToPlain(math);
    return plain ? inlineCode(plain) : _match;
  });

  return result;
}

/**
 * Replace LaTeX math with markdown code fences / inline backticks.
 * Preserves existing `inline` and ```fence``` code untouched.
 */
export function normalizeLatexInMarkdown(content: string): string {
  if (!content) return content;

  const { text: protectedText, slots } = protectMarkdownCode(content);
  if (!hasLatexMathDelimiters(protectedText)) {
    return content;
  }

  const normalized = normalizeLatexCore(protectedText);
  return restoreMarkdownCode(normalized, slots);
}
