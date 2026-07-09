<script setup lang="ts">
import { computed } from 'vue';
import { getFileTypeIconPreset } from '~/composables/common/useFileTypeIconPreset';
import { getExtension } from '~/utils/file';

const props = defineProps<{
  /** Original filename; used to infer extension when `extension` is omitted. */
  name: string;
  /** Optional uppercase extension (e.g. from `ChatPanelFile.extension`). */
  extension?: string;
  /** When set (e.g. object URL for an image `File`), shows a thumbnail instead of the type icon. */
  thumbnailSrc?: string;
  /** Extra classes on the outer tile (e.g. `mr-3 shadow-sm`). */
  tileClass?: string;
}>();

const ext = computed(() => {
  const e = props.extension?.trim();
  if (e) return e.toUpperCase();
  return getExtension(props.name || '');
});

const preset = computed(() => getFileTypeIconPreset(ext.value));

const showThumb = computed(() => Boolean(props.thumbnailSrc));
</script>

<template>
  <div
    :class="[
      'flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-lg',
      showThumb ? 'bg-gray-100 dark:bg-zinc-800' : preset.boxClass,
      tileClass,
    ]"
  >
    <v-img v-if="showThumb && thumbnailSrc" :src="thumbnailSrc" cover class="h-full w-full" />
    <v-icon v-else :icon="preset.icon" size="20" class="text-white opacity-95" />
  </div>
</template>
