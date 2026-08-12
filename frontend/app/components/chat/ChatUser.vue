<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { ChevronDownIcon, ChevronUpIcon } from 'lucide-vue-next';
import type { Message } from '~/types/message';
import ChatAction from '~/components/common/ChatAction.vue';
import FilePreview from '~/components/common/FilePreview.vue';
import { parseUserContinuation } from '~/utils/chat/parseUserContinuation';

const props = defineProps<{
  message: Message;
  loading?: boolean;
}>();

const emit = defineEmits<{
  (e: 'edit', messageId: string): void;
}>();

const { theme } = useAppTheme();
const activeThemeName = computed(() => theme.value);

const showUserActions = computed(() => props.message.role === 'user' && !props.loading);
const displayContent = computed(() => parseUserContinuation(props.message.content || '').displayText);

/** Max visible height before clamping (matches ~9–10 lines at leading-7). */
const MAX_COLLAPSED_PX = 260;

const contentRef = ref<HTMLElement | null>(null);
const needsClamp = ref(false);
const expanded = ref(false);

function updateNeedsClamp() {
  const el = contentRef.value;
  if (!el) {
    needsClamp.value = false;
    return;
  }
  needsClamp.value = el.scrollHeight > MAX_COLLAPSED_PX;
  if (!needsClamp.value) {
    expanded.value = false;
  }
}

let resizeObserver: ResizeObserver | null = null;

onMounted(async () => {
  await nextTick();
  updateNeedsClamp();
  if (typeof ResizeObserver === 'undefined' || !contentRef.value) return;
  resizeObserver = new ResizeObserver(() => {
    updateNeedsClamp();
  });
  resizeObserver.observe(contentRef.value);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  resizeObserver = null;
});

watch(
  displayContent,
  async () => {
    expanded.value = false;
    await nextTick();
    updateNeedsClamp();
  },
);

function toggleExpanded() {
  expanded.value = !expanded.value;
}
</script>

<template>
  <div class="group/user relative flex max-w-[85%] flex-col items-end pr-4 md:max-w-[70%]">
    <div v-if="message.files && message.files.length > 0" class="flex w-full justify-end">
      <FilePreview :files="message.files" readonly />
    </div>

    <v-sheet
      class="w-full min-w-0 rounded-xl rounded-br-none bg-gray-100! px-5 py-3 text-neutral-800 transition-colors dark:bg-zinc-800! dark:text-zinc-100"
      :theme="activeThemeName"
      elevation="0"
    >
      <div class="relative">
        <div
          ref="contentRef"
          :class="[
            'text-base leading-7 whitespace-pre-wrap wrap-break-word',
            needsClamp && !expanded && 'max-h-[260px] overflow-hidden',
          ]"
        >
          {{ displayContent }}
        </div>
        <div
          v-if="needsClamp && !expanded"
          class="pointer-events-none absolute inset-x-0 bottom-0 h-14 rounded-b-[inherit]  from-gray-100 to-transparent dark:from-zinc-800 dark:to-transparent"
          aria-hidden="true"
        />
      </div>

      <BaseButton
        v-if="needsClamp"
        variant="text"
        block
        :append-icon="expanded ? ChevronUpIcon : ChevronDownIcon"
        custom-class="mt-2 text-sm font-medium text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-100"
        @click="toggleExpanded"
      >
        {{ expanded ? 'Show less' : 'Show more' }}
      </BaseButton>
    </v-sheet>

    <div class="mt-2 opacity-0 transition-opacity group-hover/user:opacity-100">
      <ChatAction
        v-if="showUserActions"
        :message="message"
        @edit="(messageId) => emit('edit', String(messageId))"
      />
    </div>
  </div>
</template>
