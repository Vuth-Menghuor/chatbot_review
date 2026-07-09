export function stripHtml(value: unknown): string {
  if (typeof value !== 'string') return String(value ?? '');
  return value.replace(/<[^>]*>/g, '');
}
