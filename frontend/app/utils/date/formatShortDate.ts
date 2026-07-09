import { format, isValid, parseISO } from 'date-fns';

export function formatShortDate(dateStr: string): string {
  const date = parseISO(dateStr);
  if (!isValid(date)) return '';
  return format(date, 'MMM d');
}
