<script setup lang="ts">
import { XIcon, DownloadIcon, FileWarningIcon } from 'lucide-vue-next';
import BaseIconButton from '~/components/base/BaseIconButton.vue';
import BaseDialog from '~/components/base/BaseDialog.vue';
import FileTypeIconBadge from '~/components/common/FileTypeIconBadge.vue';
import { useFilePreview } from '~/composables/common/useFilePreview';

withDefaults(
  defineProps<{
    /** Live `File` objects or snapshots restored from storage (name/type only). */
    files: readonly unknown[];
    readonly?: boolean;
  }>(),
  {
    readonly: false,
  },
);

const emit = defineEmits<{
  (e: 'remove', index: number): void;
}>();

const {
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
} = useFilePreview(emit);
</script>

<template>
  <div v-if="files.length > 0" class="flex flex-wrap gap-3 mb-4 px-1">
    <div v-for="(file, i) in files" :key="i" class="relative group">
      <!-- Card Container -->
      <div
        class="flex items-center px-2 py-1.5 pr-4 min-w-50 max-w-70 hover:cursor-pointer transition-all border border-gray-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 rounded-xl hover:border-gray-300 dark:hover:border-zinc-700"
        @click="openPreview(file)"
      >
        <FileTypeIconBadge
          :name="fileName(file)"
          :thumbnail-src="getImageUrl(file)"
          tile-class="mr-3 shadow-sm"
        />

        <!-- Info -->
        <div class="flex-1 flex flex-col min-w-0">
          <span
            class="text-sm font-semibold text-gray-900 dark:text-zinc-100 truncate leading-tight"
          >
            {{ fileName(file) }}
          </span>
          <span
            class="text-[10px] font-bold text-gray-400 dark:text-zinc-500 uppercase tracking-tighter -mt-1"
          >
            {{ getFileType(file) }}
          </span>
        </div>

        <!-- Close Button (Remove from list) -->
        <div v-if="!readonly" class="absolute -top-2 -right-2 z-10">
          <BaseIconButton
            :icon="XIcon"
            size="x-small"
            width="20"
            height="20"
            custom-class="bg-gray-900 text-white hover:bg-gray-700 rounded-full border border-white dark:border-zinc-800 shadow-md"
            @click.stop="removeAt(i)"
          />
        </div>
      </div>
    </div>
  </div>

  <!-- Full Preview Dialog -->
  <BaseDialog
    v-model="showPreviewDialog"
    :title="activeFileTitle"
    :width="1200"
    :on-close="closePreview"
  >
    <div class="-m-6 flex items-center justify-center overflow-hidden bg-white dark:bg-zinc-950">
      <template v-if="activeFile">
        <!-- Image Full View -->
        <div
          v-if="isImage(activeFile)"
          class="relative w-full h-full flex items-center justify-center p-4 object-cover object-fit"
        >
          <v-img :src="previewUrl" class="h-full w-auto" />
        </div>

        <!-- PDF Full View -->
        <iframe
          v-else-if="previewUrl && activeFileTitle.toLowerCase().endsWith('.pdf')"
          :src="previewUrl"
          class="w-full h-[80vh] border-none"
        ></iframe>
        <!-- Fallback -->
        <div v-else class="flex flex-col items-center gap-6 py-20">
          <div
            class="w-20 h-20 rounded-full bg-gray-100 dark:bg-zinc-900 flex items-center justify-center"
          >
            <FileWarningIcon class="lucide h-10 w-10 text-gray-300 dark:text-zinc-600" />
          </div>
          <span class="text-gray-500 font-medium">Preview not available for this file type.</span>
          <BaseButton
            variant="flat"
            color="black"
            custom-class="rounded-xl px-6"
            :prepend-icon="DownloadIcon"
            :href="previewUrl"
            download
          >
            Download instead
          </BaseButton>
        </div>
      </template>
    </div>
  </BaseDialog>
</template>
