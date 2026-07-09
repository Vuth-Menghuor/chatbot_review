import { ref, computed, unref } from 'vue';
import type { Ref } from 'vue';
import type { MessageBlock } from '~/types/message';
import { useClipboardCopy } from '~/composables/common/useClipboardCopy';

type ImageBlockContent = {
  imageUrl?: unknown;
  url?: unknown;
  src?: unknown;
  prompt?: unknown;
  loading?: unknown;
  error?: unknown;
  status?: unknown;
  title?: unknown;
  subtitle?: unknown;
};

/**
 * useImageRenderer
 * Image URL, prompt, and error payload come from API `content` only.
 */
export function useImageRenderer(
  block: MessageBlock | Ref<MessageBlock>,
  emit: (event: 'regenerate', id: string) => void,
) {
  const imageLoaded = ref(false);
  const imageError = ref(false);
  const { copied: copiedPrompt, copyText } = useClipboardCopy({ resetMs: 1200 });
  const currentBlock = computed(() => unref(block));

  const content = computed<ImageBlockContent>(() =>
    currentBlock.value.content &&
    typeof currentBlock.value.content === 'object' &&
    !Array.isArray(currentBlock.value.content)
      ? (currentBlock.value.content as ImageBlockContent)
      : {},
  );

  const isLoading = computed(() => {
    const status = String(content.value.status || '').toLowerCase();
    return Boolean(content.value.loading || status === 'pending' || status === 'processing');
  });

  const isError = computed(() => Boolean(content.value.error) || imageError.value);

  const imageUrl = computed(() => {
    if (typeof currentBlock.value.content === 'string') return currentBlock.value.content;
    const value = content.value.imageUrl ?? content.value.url ?? content.value.src;
    return typeof value === 'string' && value.trim() ? value : undefined;
  });

  const prompt = computed(() => {
    const value = content.value.prompt;
    return typeof value === 'string' ? value : '';
  });

  const hasStructuredApiError = computed(() => {
    const err = content.value.error;
    if (err && typeof err === 'object' && !Array.isArray(err)) return true;
    return typeof err === 'string' && err.trim().length > 0;
  });

  const errorBlock = computed((): MessageBlock => {
    const b = currentBlock.value;
    const id = String(b.id ?? 'image');
    const err = content.value.error;
    if (err && typeof err === 'object' && !Array.isArray(err)) {
      return { id: `${id}-error`, type: 'error', content: err as Record<string, unknown> };
    }
    if (typeof err === 'string' && err.trim()) {
      return { id: `${id}-error`, type: 'error', content: { message: err.trim() } };
    }
    return { id: `${id}-error`, type: 'error', content: {} };
  });

  const canUseImageActions = computed(() =>
    Boolean(imageUrl.value && imageLoaded.value && !isError.value),
  );

  const onImageLoad = () => {
    imageLoaded.value = true;
    imageError.value = false;
  };

  const onImageError = () => {
    imageLoaded.value = false;
    imageError.value = true;
  };

  const handleDownload = async () => {
    if (!imageUrl.value) return;
    try {
      const response = await fetch(imageUrl.value);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `gdce-image-${Date.now()}.jpg`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      if (imageUrl.value) window.open(imageUrl.value, '_blank');
    }
  };

  const handleRegenerate = () => {
    if (currentBlock.value.id) emit('regenerate', currentBlock.value.id);
  };

  const openImage = () => {
    if (!imageUrl.value) return;
    window.open(imageUrl.value, '_blank', 'noopener,noreferrer');
  };

  const copyPrompt = async () => {
    if (!prompt.value) return;
    await copyText(String(prompt.value));
  };

  return {
    imageLoaded,
    copiedPrompt,
    isLoading,
    isError,
    imageUrl,
    prompt,
    hasStructuredApiError,
    errorBlock,
    canUseImageActions,
    onImageLoad,
    onImageError,
    handleDownload,
    handleRegenerate,
    openImage,
    copyPrompt,
  };
}
