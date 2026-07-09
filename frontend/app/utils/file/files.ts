import type { ChatPanelFile, Message } from '~/types/message';

export function getFileValue(file: unknown, key: string) {
  if (!file || typeof file !== 'object') return undefined;
  return (file as Record<string, unknown>)[key];
}

export function formatFileSize(size: unknown) {
  if (typeof size !== 'number' || Number.isNaN(size)) return 'Unknown size';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatFileDate(value: unknown, fallback?: string) {
  const dateSource = typeof value === 'number' ? value : fallback;
  if (!dateSource) return 'Unknown date';

  const date = new Date(dateSource);
  if (Number.isNaN(date.getTime())) return 'Unknown date';

  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

export function getExtension(name: string) {
  const dotIndex = name.lastIndexOf('.');
  if (dotIndex === -1) return 'FILE';
  return name.slice(dotIndex + 1).toUpperCase() || 'FILE';
}

/** True when the attachment still has in-memory bytes (not a JSON snapshot after reload). */
export function canDownloadChatFileRaw(raw: unknown): raw is File | Blob {
  return raw instanceof File || raw instanceof Blob;
}

/** Trigger a browser save for a `File` or `Blob`. No-op for metadata-only objects. */
export function downloadChatFileRaw(raw: unknown, preferredFilename: string): boolean {
  if (!import.meta.client || !canDownloadChatFileRaw(raw)) return false;

  const downloadName =
    raw instanceof File && raw.name.trim()
      ? raw.name.trim()
      : preferredFilename.trim() || 'download';

  const objectUrl = URL.createObjectURL(raw);
  try {
    const a = document.createElement('a');
    a.href = objectUrl;
    a.download = downloadName;
    a.rel = 'noopener';
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 2000);
  }
  return true;
}

export function toChatPanelFile(
  file: unknown,
  message: Message,
  index: number,
): ChatPanelFile | null {
  const name = getFileValue(file, 'name');
  if (typeof name !== 'string' || !name.trim()) return null;

  return {
    id: `${message.id ?? 'message'}-${index}-${name}`,
    name,
    sizeLabel: formatFileSize(getFileValue(file, 'size')),
    dateLabel: formatFileDate(getFileValue(file, 'lastModified'), message.createdAt),
    extension: getExtension(name),
    raw: file,
  };
}

export function serializeFileForStorage(file: unknown) {
  if (!file || typeof file !== 'object') return file;

  const value = file as Record<string, unknown>;
  if (!('name' in value)) return file;

  return {
    name: value.name,
    size: value.size,
    type: value.type,
    lastModified: value.lastModified,
    file_id: value.file_id,
    url: value.url,
    object_key: value.object_key,
    bucket: value.bucket,
    status: value.status,
  };
}

export function serializeMessagesForStorage(messages: Message[]) {
  return messages.map((message) => ({
    ...message,
    files: message.files?.map(serializeFileForStorage),
  }));
}
