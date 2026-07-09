/** Coerce runtime config / env values to boolean (supports `"true"`, `"1"`, etc.). */
export function toBoolean(value: unknown, fallback = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (!normalized) return fallback;
    return ['1', 'true', 'yes', 'on'].includes(normalized);
  }
  if (value == null) return fallback;
  return Boolean(value);
}
