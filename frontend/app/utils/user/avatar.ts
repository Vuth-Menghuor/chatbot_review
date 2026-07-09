export function getInitials(name?: string, length = 2) {
  const source = (name || '').trim();
  if (!source) return 'U';

  return source
    .split(/\s+/)
    .map((s) => (s ? s[0] : ''))
    .join('')
    .slice(0, length)
    .toUpperCase();
}

export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}
