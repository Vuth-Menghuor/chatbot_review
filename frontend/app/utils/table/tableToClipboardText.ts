import { stripHtml } from './stripHtml';

export interface ClipboardColumn {
  key: string;
  title: unknown;
}

export type ClipboardRow = Record<string, unknown>;

export function tableToClipboardText(columns: ClipboardColumn[], rows: ClipboardRow[]): string {
  if (!columns.length || !rows.length) return '';

  const header = columns.map((column) => stripHtml(column.title)).join('\t');
  const body = rows
    .map((row) => columns.map((column) => stripHtml(row[column.key])).join('\t'))
    .join('\n');

  return `${header}\n${body}`;
}
