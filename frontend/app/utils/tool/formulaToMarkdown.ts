import { resolveCalculatorLabels, type CalculatorMarkdownLabels } from './formulaLabels';

function fenceCode(lang: string, code: string): string {
  const trimmed = code.trim();
  if (!trimmed) return '';
  return `\`\`\`${lang}\n${trimmed}\n\`\`\``;
}

function inlineCode(text: string): string {
  return `\`${text.replace(/`/g, '\\`')}\``;
}

function stepRecord(step: Record<string, unknown>, labels: CalculatorMarkdownLabels): string {
  const label = step.label ?? step.title ?? labels.step;
  const value = step.value ?? step.expression;
  const note = step.note;
  if (value != null && String(value).trim()) {
    const suffix = note ? ` — ${note}` : '';
    return `- **${label}:** ${inlineCode(String(value))}${suffix}`;
  }
  return `- ${label}`;
}

/** Convert calculator tool payload → markdown with highlighted formula code blocks. */
export function calculatorDataToMarkdown(data: unknown, locale?: string): string {
  if (typeof data === 'string') return data.trim();
  if (data == null) return '';
  if (typeof data !== 'object') return String(data);

  const labels = resolveCalculatorLabels(locale);
  const obj = data as Record<string, unknown>;
  const parts: string[] = [];

  const title = obj.title ?? obj.name;
  if (title) parts.push(`### ${title}`);

  if (obj.description) parts.push(String(obj.description));

  const expression = obj.expression;
  if (expression != null && String(expression).trim()) {
    parts.push(`**${labels.expression}**`);
    parts.push(fenceCode('excel', String(expression)));
  }

  const formula = obj.formula;
  if (formula != null && String(formula).trim() && formula !== expression) {
    parts.push(`**${labels.formula}**`);
    parts.push(fenceCode('text', String(formula)));
  }

  if (obj.result !== undefined && obj.result !== null && obj.result !== '') {
    const unit = obj.unit ?? obj.currency ?? '';
    parts.push(`**${labels.result}:** ${obj.result}${unit ? ` ${unit}` : ''}`);
  }

  const steps = obj.steps;
  if (Array.isArray(steps) && steps.length > 0) {
    parts.push(`**${labels.steps}**`);
    for (const step of steps) {
      if (typeof step === 'string') {
        parts.push(`- ${inlineCode(step)}`);
      } else if (step && typeof step === 'object') {
        parts.push(stepRecord(step as Record<string, unknown>, labels));
      }
    }
  }

  if (obj.note) {
    parts.push(`**${labels.note}**`);
    parts.push(String(obj.note));
  }

  return parts.filter(Boolean).join('\n\n');
}

/** Convert math/formula tool payload → markdown inline or fenced code (no MathJax). */
export function mathDataToMarkdown(data: unknown): string {
  if (typeof data === 'string') {
    const trimmed = data.trim();
    if (!trimmed) return '';
    const stripped = trimmed.replace(/^\$\$|\$\$$/g, '').trim();
    if (trimmed.includes('\n') || stripped.length > 72) {
      return fenceCode('text', stripped);
    }
    return inlineCode(stripped);
  }

  if (data == null || typeof data !== 'object') return String(data ?? '');

  const obj = data as Record<string, unknown>;
  const text = String(obj.latex ?? obj.expression ?? obj.formula ?? obj.content ?? '').trim();
  if (!text) return '';
  return mathDataToMarkdown(text);
}

export function isCalculatorRawType(type: string): boolean {
  const t = type.trim().toLowerCase();
  return t === 'calculator' || t === 'calc';
}

export function isMathRawType(type: string): boolean {
  const t = type.trim().toLowerCase();
  return t === 'math' || t === 'latex' || t === 'formula' || t === 'equation' || t === 'mathjax';
}

export function legacyToolContentToMarkdown(
  rawType: string,
  content: unknown,
  locale?: string,
): string | null {
  if (isCalculatorRawType(rawType)) return calculatorDataToMarkdown(content, locale);
  if (isMathRawType(rawType)) return mathDataToMarkdown(content);
  return null;
}
