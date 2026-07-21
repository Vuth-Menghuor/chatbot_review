<template>
  <aside
    class="h-full border-l border-gray-100 dark:border-zinc-800 bg-white dark:bg-[#0a0a0a] transition-all duration-300 ease-in-out shrink-0 overflow-hidden flex flex-col z-10"
    :class="[
      uiStore.filesPanelOpened ? 'w-[360px] border-l' : 'w-0 border-none pointer-events-none',
      uiStore.isMobile ? 'fixed right-0 top-0 h-screen z-110 shadow-2xl' : 'relative',
    ]"
  >
    <!-- Header -->
    <div
      class="px-5 h-14 flex items-center justify-between border-b border-gray-100 dark:border-zinc-800/50 sticky top-0 bg-inherit z-10 shrink-0"
    >
      <div class="flex items-center gap-3">
        <BaseTabs
          v-model="activeTabModel"
          :items="filePanelTabs"
          variant="pill"
          class="!mb-0 [&>div:first-child]:mb-0"
        >
          <template #files />
          <template #sources />
        </BaseTabs>
      </div>
      <BaseIconButton
        :icon="XIcon"
        size="small"
        custom-class="text-gray-400 hover:text-gray-600 dark:hover:text-zinc-200"
        @click="uiStore.filesPanelOpened = false"
      />
    </div>

    <!-- ─── FILES TAB ──────────────────────────────────────────── -->
    <div v-if="activeTab === 'files'" class="flex-1 overflow-y-auto custom-scrollbar">
      <div v-if="files.length" class="px-3 pt-3 pb-2 flex flex-col gap-2">
        <div
          v-for="file in files"
          :key="file.id"
          class="group flex items-center gap-3 rounded-lg border border-gray-200 bg-white p-3 transition-colors dark:border-zinc-700 dark:bg-zinc-900/40 hover:bg-gray-50/90 dark:hover:bg-zinc-800/60"
        >
          <FileTypeIconBadge :name="file.name" :extension="file.extension" />

          <div class="min-w-0 flex-1 flex flex-col justify-center gap-0.5">
            <span
              class="truncate text-sm font-bold text-gray-900 dark:text-zinc-100"
              :title="file.name"
            >
              {{ file.name }}
            </span>
            <span class="text-xs text-gray-500 dark:text-zinc-400">
              <span class="font-medium uppercase tracking-wide text-gray-600 dark:text-zinc-300">
                {{ file.extension || 'FILE' }}
              </span>
              <span class="text-gray-400 dark:text-zinc-500">
                · {{ file.sizeLabel }} · {{ file.dateLabel }}</span
              >
            </span>
          </div>

          <div
            class="flex shrink-0 items-center opacity-0 transition-all group-hover:translate-x-0 group-hover:opacity-100 translate-x-1"
          >
            <BaseIconButton
              :icon="DownloadIcon"
              size="small"
              :disabled="!canDownloadChatFileRaw(file.raw)"
              :tooltip="
                canDownloadChatFileRaw(file.raw)
                  ? $t('chat.actions.download')
                  : $t('chat.actions.downloadUnavailable')
              "
              custom-class="text-gray-400 hover:text-blue-500 dark:hover:text-blue-400"
              @click.stop="downloadChatPanelFile(file)"
            />
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div
        v-else
        class="h-full flex flex-col items-center justify-center text-center p-8 opacity-60"
      >
        <div
          class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-white dark:bg-zinc-800/50"
        >
          <LibraryIcon class="w-8 h-8 text-gray-300 dark:text-zinc-700" />
        </div>
        <p class="text-[13px] text-gray-500 dark:text-zinc-400 font-medium">
          {{ $t('chat.filesPanel.noFilesTitle') }}
        </p>
        <p class="mt-1 text-[11px] text-gray-400 dark:text-zinc-600">
          {{ $t('chat.filesPanel.noFilesHint') }}
        </p>
      </div>
    </div>

    <!-- ─── SOURCES TAB ──────────────────────────────────────────── -->
    <div v-else class="flex-1 overflow-y-auto custom-scrollbar">
      <div v-if="activeSources.length" class="px-4 pt-4 pb-6 flex flex-col gap-1">
        <!-- Section header -->
        <div class="flex items-center gap-2 mb-3">
          <BookOpenIcon class="w-4 h-4 text-neutral-400 dark:text-zinc-500" />
          <span
            class="text-xs font-semibold text-neutral-500 dark:text-zinc-400 uppercase tracking-wider"
          >
            {{ $t('chat.filesPanel.sourcesCount', { count: activeSources.length }) }}
          </span>
        </div>

        <!-- Source Cards -->
        <a
          v-for="(source, idx) in activeSources"
          :key="idx"
          :href="source.url || undefined"
          target="_blank"
          rel="noopener noreferrer"
          class="group flex gap-3 p-3 rounded-xl border border-neutral-100 dark:border-zinc-800/80 hover:border-neutral-200 dark:hover:border-zinc-700 hover:bg-neutral-50/70 dark:hover:bg-zinc-900/50 transition-all duration-150 no-underline cursor-pointer"
          :class="!source.url ? 'pointer-events-none' : ''"
        >
          <!-- Favicon -->
          <div
            class="shrink-0 w-8 h-8 rounded-lg bg-neutral-100 dark:bg-zinc-800 flex items-center justify-center overflow-hidden mt-0.5"
          >
            <img
              v-if="source.domain || source.url"
              :src="`https://www.google.com/s2/favicons?domain=${source.domain || getDomain(source.url)}&sz=32`"
              :alt="source.domain || getDomain(source.url)"
              class="w-5 h-5 object-contain"
              @error="($event.target as HTMLImageElement).style.display = 'none'"
            />
            <GlobeIcon v-else class="w-4 h-4 text-neutral-400 dark:text-zinc-500" />
          </div>

          <!-- Text -->
          <div class="min-w-0 flex-1">
            <!-- Domain label -->
            <p
              class="text-[10px] font-semibold text-neutral-400 dark:text-zinc-500 uppercase tracking-wide mb-0.5"
            >
              {{ sourceSubtitle(source) }}
            </p>
            <!-- Title -->
            <p
              class="text-sm font-bold text-gray-900 dark:text-zinc-100 leading-snug line-clamp-2 group-hover:text-primary transition-colors"
            >
              {{ source.title }}
            </p>
            <!-- Snippet -->
            <p
              v-if="source.snippet"
              class="mt-1 text-xs text-neutral-500 dark:text-zinc-400 line-clamp-2 leading-relaxed"
              :title="source.snippet"
            >
              {{ sourcePreviewSnippet(source.snippet) }}
            </p>
          </div>

          <!-- External link indicator -->
          <ExternalLinkIcon
            v-if="source.url"
            class="w-3.5 h-3.5 text-neutral-300 dark:text-zinc-600 group-hover:text-primary transition-colors shrink-0 mt-1"
          />
        </a>
      </div>

      <!-- Sources Empty State -->
      <div
        v-else
        class="h-full flex flex-col items-center justify-center text-center p-8 opacity-60"
      >
        <div
          class="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-white dark:bg-zinc-800/50"
        >
          <BookOpenIcon class="w-8 h-8 text-gray-300 dark:text-zinc-700" />
        </div>
        <p class="text-[13px] text-gray-500 dark:text-zinc-400 font-medium">
          {{ $t('chat.filesPanel.noSourcesTitle') }}
        </p>
        <p class="mt-1 text-[11px] text-gray-400 dark:text-zinc-600">
          {{ $t('chat.filesPanel.noSourcesHint') }}
        </p>
      </div>
    </div>

    <!-- Mobile Mask -->
    <div
      v-if="uiStore.isMobile && uiStore.filesPanelOpened"
      @click="uiStore.filesPanelOpened = false"
    />
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import {
  XIcon,
  DownloadIcon,
  LibraryIcon,
  BookOpenIcon,
  ExternalLinkIcon,
  GlobeIcon,
} from 'lucide-vue-next';
import { useUiStore } from '~/stores/ui.store';
import { useChatFiles } from '~/composables/filepanel/useChatFiles';
import FileTypeIconBadge from '~/components/common/FileTypeIconBadge.vue';
import type { ChatPanelFile, MessageSource } from '~/types/message';
import { canDownloadChatFileRaw, downloadChatFileRaw } from '~/utils/file';
import { getDomain } from '~/utils/source';

const uiStore = useUiStore();
const { files } = useChatFiles();

const { t } = useI18n();

const activeTabModel = computed({
  get: () => uiStore.activePanelType,
  set: (value: 'files' | 'sources') => {
    uiStore.activePanelType = value;
  },
});

const activeTab = computed(() => uiStore.activePanelType);

const activeSources = computed<MessageSource[]>(() => {
  return (uiStore.activeMessageForSources?.sources as MessageSource[] | undefined) ?? [];
});

const sourcesCount = computed(() => activeSources.value.length);

const filePanelTabs = computed(() => [
  { title: t('chat.filesPanel.files'), value: 'files' },
  {
    title:
      sourcesCount.value > 0
        ? `${t('chat.filesPanel.sources')} (${sourcesCount.value})`
        : t('chat.filesPanel.sources'),
    value: 'sources',
  },
]);

function sourceSubtitle(source: MessageSource) {
  const parts = [
    source.documentId,
    source.chunkIndex !== undefined ? `Chunk ${source.chunkIndex}` : undefined,
  ].filter(Boolean);
  if (parts.length) return parts.join(' · ');
  return source.domain || getDomain(source.url) || t('chat.filesPanel.sourceLabel');
}

function sourcePreviewSnippet(snippet: string) {
  const tablePreview = tableSnippetPreview(snippet);
  if (tablePreview) return tablePreview;

  return snippet
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180);
}

function tableSnippetPreview(snippet: string) {
  const lines = snippet
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.includes('|') && !/^[:\-\s|]+$/.test(line));

  const rows = lines
    .map((line) =>
      line
        .split('|')
        .map((cell) => cell.trim())
        .filter(Boolean),
    )
    .filter((cells) => cells.length);

  const dataRow = rows.find((cells) => cells.some((cell) => !/^field\s+no$/i.test(cell) && !/^field\s+label$/i.test(cell)));
  if (!dataRow) return '';

  const meaningfulCells = dataRow.filter((cell) => !/^(field no|field label|action|description and \/ or usage)$/i.test(cell));
  if (!meaningfulCells.length) return 'Declaration field requirements and usage notes.';

  const [label, action, description] = meaningfulCells;
  return [label, action, description].filter(Boolean).join(' — ').replace(/\s+/g, ' ').slice(0, 180);
}

function downloadChatPanelFile(file: ChatPanelFile) {
  downloadChatFileRaw(file.raw, file.name);
}
</script>
