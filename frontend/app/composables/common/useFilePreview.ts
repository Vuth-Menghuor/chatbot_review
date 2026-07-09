import { computed, onUnmounted, ref } from 'vue';

import type { FilePreviewEmit } from '~/types/message';
export function useFilePreview(emit: FilePreviewEmit) {
  const urlMap = new Map<File, string>();

  function fileName(f: unknown): string {
    if (
      f &&
      typeof f === 'object' &&
      'name' in f &&
      typeof (f as { name: unknown }).name === 'string'
    ) {
      return (f as { name: string }).name;
    }
    return '';
  }

  const getImageUrl = (file: unknown) => {
    if (!(file instanceof File) || !file.type.startsWith('image/')) return undefined;
    if (!urlMap.has(file)) {
      urlMap.set(file, URL.createObjectURL(file));
    }
    return urlMap.get(file);
  };

  onUnmounted(() => {
    urlMap.forEach((url) => URL.revokeObjectURL(url));
    urlMap.clear();
  });

  const getFileType = (file: unknown) => {
    const name = fileName(file);
    const dotIndex = name.lastIndexOf('.');
    if (dotIndex !== -1) {
      const ext = name.slice(dotIndex + 1).toUpperCase();
      return ext || 'FILE';
    }
    return 'FILE';
  };

  const showPreviewDialog = ref(false);
  const activeFile = ref<unknown>(null);
  const previewUrl = ref('');

  const isImage = (file: unknown) => !!getImageUrl(file);

  const openPreview = (file: unknown) => {
    activeFile.value = file;
    if (isImage(file)) {
      previewUrl.value = getImageUrl(file) || '';
    } else if (file instanceof File) {
      const n = fileName(file).toLowerCase();
      if (file.type === 'application/pdf' || n.endsWith('.pdf')) {
        previewUrl.value = URL.createObjectURL(file);
      }
    }
    showPreviewDialog.value = true;
  };

  const closePreview = () => {
    if (activeFile.value && !isImage(activeFile.value) && previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value);
    }
    showPreviewDialog.value = false;
    activeFile.value = null;
    previewUrl.value = '';
  };

  const activeFileTitle = computed(() => fileName(activeFile.value));

  const removeAt = (index: number) => emit('remove', index);

  return {
    fileName,
    getImageUrl,
    getFileType,
    isImage,
    showPreviewDialog,
    activeFile,
    previewUrl,
    openPreview,
    closePreview,
    activeFileTitle,
    removeAt,
  };
}
