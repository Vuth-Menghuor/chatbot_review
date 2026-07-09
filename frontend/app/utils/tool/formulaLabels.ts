import en from '../../../i18n/locales/en.json';
import km from '../../../i18n/locales/km.json';

export interface CalculatorMarkdownLabels {
  expression: string;
  formula: string;
  result: string;
  steps: string;
  note: string;
  step: string;
}

const LOCALE_LABELS: Record<string, CalculatorMarkdownLabels> = {
  en: {
    expression: en.calculator.expression,
    formula: en.calculator.tabs.formula,
    result: en.calculator.finalResult,
    steps: en.calculator.tabs.steps,
    note: en.calculator.tabs.note,
    step: en.calculator.stepFallback,
  },
  km: {
    expression: km.calculator.expression,
    formula: km.calculator.tabs.formula,
    result: km.calculator.finalResult,
    steps: km.calculator.tabs.steps,
    note: km.calculator.tabs.note,
    step: km.calculator.stepFallback,
  },
};

export function resolveCalculatorLabels(locale?: string): CalculatorMarkdownLabels {
  const key = String(locale || 'en').split('-')[0]?.toLowerCase() || 'en';
  return LOCALE_LABELS[key] ?? LOCALE_LABELS.en!;
}
