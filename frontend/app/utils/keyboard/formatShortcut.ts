export function isMacPlatform(): boolean {
  if (!import.meta.client) return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.platform);
}

export function formatModKey(): string {
  return isMacPlatform() ? '⌘' : 'Ctrl';
}

export function formatShortcut(parts: string[]): string {
  return parts.join(' ');
}
