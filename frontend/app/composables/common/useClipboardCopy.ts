import { onBeforeUnmount, ref } from 'vue';

interface ClipboardCopyOptions {
  resetMs?: number;
  fallbackToTextarea?: boolean;
}

function copyWithTextareaFallback(text: string): boolean {
  const el = document.createElement('textarea');
  el.value = text;
  el.setAttribute('readonly', '');
  el.style.position = 'fixed';
  el.style.opacity = '0';
  document.body.appendChild(el);
  el.select();
  try {
    return document.execCommand('copy');
  } finally {
    document.body.removeChild(el);
  }
}

export function stringifyClipboardContent(content: string | object): string {
  return typeof content === 'object' ? JSON.stringify(content, null, 2) : String(content);
}

export function useClipboardCopy(options: ClipboardCopyOptions = {}) {
  const copied = ref(false);
  const resetMs = options.resetMs ?? 2000;
  let resetTimer: ReturnType<typeof setTimeout> | undefined;

  const clearResetTimer = () => {
    if (!resetTimer) return;
    clearTimeout(resetTimer);
    resetTimer = undefined;
  };

  const scheduleReset = () => {
    clearResetTimer();
    resetTimer = setTimeout(() => {
      copied.value = false;
      resetTimer = undefined;
    }, resetMs);
  };

  const copyText = async (text: string): Promise<boolean> => {
    // Clipboard API access is restricted to secure contexts (HTTPS or
    // localhost). Use the synchronous fallback immediately on LAN HTTP pages
    // so it still executes within the user's click gesture.
    const canUseClipboardApi =
      typeof navigator !== 'undefined' &&
      window.isSecureContext &&
      typeof navigator.clipboard?.writeText === 'function';

    if (!canUseClipboardApi && options.fallbackToTextarea) {
      const success = copyWithTextareaFallback(text);
      copied.value = success;
      if (success) scheduleReset();
      return success;
    }

    try {
      await navigator.clipboard.writeText(text);
      copied.value = true;
      scheduleReset();
      return true;
    } catch {
      if (!options.fallbackToTextarea) {
        copied.value = false;
        return false;
      }

      const success = copyWithTextareaFallback(text);
      copied.value = success;
      if (success) scheduleReset();
      return success;
    }
  };

  onBeforeUnmount(clearResetTimer);

  return {
    copied,
    copyText,
  };
}
