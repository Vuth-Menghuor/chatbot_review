import { onBeforeUnmount, ref } from 'vue';

interface ClipboardCopyOptions {
  resetMs?: number;
  fallbackToTextarea?: boolean;
}

function copyWithTextareaFallback(text: string): boolean {
  const el = document.createElement('textarea');
  el.value = text;
  document.body.appendChild(el);
  el.select();
  document.execCommand('copy');
  document.body.removeChild(el);
  return true;
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
