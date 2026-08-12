export interface TableColumnLike {
  key: string;
  title?: unknown;
  label?: unknown;
}

export type TableRowLike = Record<string, unknown>;

const HIDDEN_CONFIDENCE_KEYS = new Set([
  'candidate_confidence',
  'confidence',
  'confidence_label',
  'llm_confidence',
  'match_score',
  'relevance_score',
  'retrieval_score',
  'similarity_score',
]);

function normalizedKey(value: unknown): string {
  return String(value ?? '')
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[\s-]+/g, '_')
    .toLowerCase();
}

function normalizedLabel(value: unknown): string {
  return String(value ?? '').trim().replace(/\s+/g, ' ').toLowerCase();
}

export function isHiddenTableColumn(column: TableColumnLike): boolean {
  const key = normalizedKey(column.key);
  if (HIDDEN_CONFIDENCE_KEYS.has(key)) return true;

  const label = normalizedLabel(column.title ?? column.label);
  return /\b(confidence|match score|retrieval score|similarity score|relevance score)\b/.test(label);
}

export function filterVisibleTableColumns<T extends TableColumnLike>(columns: T[]): T[] {
  return columns.filter((column) => !isHiddenTableColumn(column));
}

export function hiddenTableColumnKeys(columns: TableColumnLike[]): Set<string> {
  return new Set(columns.filter(isHiddenTableColumn).map((column) => column.key));
}

export function stripHiddenTableValues(
  row: TableRowLike,
  columns: TableColumnLike[] = [],
): TableRowLike {
  const hiddenKeys = hiddenTableColumnKeys(columns);
  const visibleRow: TableRowLike = {};

  for (const [key, value] of Object.entries(row)) {
    if (hiddenKeys.has(key)) continue;
    if (HIDDEN_CONFIDENCE_KEYS.has(normalizedKey(key))) continue;
    visibleRow[key] = value;
  }

  return visibleRow;
}
