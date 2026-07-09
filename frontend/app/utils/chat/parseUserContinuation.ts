export interface UserContinuation {
  requestId: string;
  toolName?: string;
  action: string;
  values: Record<string, unknown>;
}

export function parseUserContinuation(text: string): {
  displayText: string;
  continuation?: UserContinuation;
} {
  const trimmed = text.trim();
  if (!trimmed.startsWith('{')) {
    return { displayText: text };
  }
  try {
    const parsed = JSON.parse(trimmed) as {
      message?: string;
      meta?: { continuation?: UserContinuation };
    };
    const continuation = parsed.meta?.continuation;
    if (
      continuation &&
      typeof continuation.requestId === 'string' &&
      continuation.requestId.trim()
    ) {
      return {
        displayText:
          typeof parsed.message === 'string' && parsed.message.trim()
            ? parsed.message.trim()
            : trimmed,
        continuation: {
          requestId: continuation.requestId,
          toolName: continuation.toolName,
          action: continuation.action || 'submit',
          values: continuation.values ?? {},
        },
      };
    }
  } catch {
    /* not JSON continuation */
  }
  return { displayText: text };
}
