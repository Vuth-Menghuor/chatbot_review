<script setup lang="ts">
import { computed, ref } from 'vue';
import { FileTextIcon, Trash2Icon, FileSearchIcon } from 'lucide-vue-next';
import type { MenuItem } from '~/types/ui-menu';
import { getExtension, getFileColor } from '~/utils/file';

interface Source {
  name: string;
  type: string;
  color: string;
}

const props = defineProps<{
  sourceList: Source[];
}>();

const emit = defineEmits<{
  (e: 'remove-source', index: number): void;
  (e: 'add-source', source: Source): void;
}>();

const { t } = useI18n();
const fileInput = ref<HTMLInputElement | null>(null);
const isUploading = ref(false);

const sourceListEntries = computed<MenuItem[]>(() =>
  props.sourceList.map((source, index) => ({
    id: `${source.name}-${index}`,
    appearance: 'card',
    icon: FileTextIcon,
    leadingClass: source.color || 'bg-blue-500',
    label: source.name,
    description: `${source.type} · Ready`,
    menuItems: [
      {
        label: t('common.delete'),
        icon: Trash2Icon,
        danger: true,
        onClick: () => emit('remove-source', index),
      },
    ],
  })),
);

function triggerUpload() {
  fileInput.value?.click();
}

async function handleFileUpload(event: Event) {
  const target = event.target as HTMLInputElement;
  const files = target.files;
  if (!files || files.length === 0) return;

  isUploading.value = true;
  try {
    for (const file of Array.from(files)) {
      const newSource: Source = {
        name: file.name,
        type: getExtension(file.name),
        color: getFileColor(file.name),
      };
      emit('add-source', newSource);
    }
  } finally {
    isUploading.value = false;
    target.value = '';
  }
}

defineExpose({
  triggerUpload,
});
</script>

<template>
  <div class="flex-1 overflow-y-auto custom-scrollbar -mx-2 bg-white px-2 pb-10 dark:bg-zinc-950">
    <input ref="fileInput" type="file" class="hidden" multiple @change="handleFileUpload" />

    <BaseMenuList
      v-if="sourceListEntries.length"
      tone="nav"
      plain
      full-width
      bg-color="transparent"
      list-class="pa-0 w-full bg-transparent"
      :items="sourceListEntries"
    />

    <div
      v-else-if="!isUploading"
      class="flex min-h-full flex-col items-center justify-center px-4 py-12 text-center"
    >
      <div
        class="mb-6 flex h-20 w-20 items-center justify-center rounded-full border-2 border-dashed border-gray-200 dark:border-zinc-600"
      >
        <FileSearchIcon class="h-10 w-10 text-gray-300 dark:text-zinc-700" />
      </div>
      <h3 class="mb-2 text-lg font-semibold text-gray-900 dark:text-zinc-100">No sources available</h3>
      <p class="mx-auto mb-6 max-w-xs text-base text-gray-500 dark:text-zinc-500">
        Upload documents or paste text to provide context for your AI assistant.
      </p>
    </div>
  </div>
</template>
