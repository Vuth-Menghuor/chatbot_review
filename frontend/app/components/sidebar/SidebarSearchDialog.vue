<template>
  <BaseSearchDialog
    v-model="model"
    v-model:query="query"
    :width="640"
    :search-placeholder="$t('search.placeholder')"
    append-mode="clear"
    :show-close-icon="true"
    body-class="py-2 px-0"
  >
    <BaseMenuList
      v-if="searchListEntries.length"
      tone="menu"
      plain
      full-width
      bg-color="transparent"
      list-class="pa-0 w-full"
      :items="searchListEntries"
    />

    <div v-else class="py-20 text-center">
      <SearchIcon class="mx-auto mb-4 h-12 w-12 text-gray-200 dark:text-zinc-800" />
      <p class="font-medium text-gray-600 dark:text-zinc-400">
        {{ emptyMessage }}
      </p>
      <p v-if="query.trim()" class="mt-1 text-sm text-gray-400 dark:text-zinc-500">
        {{ $t('search.tryAdjusting') }}
      </p>
    </div>
  </BaseSearchDialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, type Component } from 'vue';
import { SearchIcon, HistoryIcon, FolderIcon } from 'lucide-vue-next';
import type { MenuEntry, MenuItem } from '~/types/ui-menu';
import { useChatStore } from '~/stores/chat.store';
import { useProjectStore } from '~/stores/project.store';
import { navigateTo } from '#imports';
import { useUiStore } from '~/stores/ui.store';
import { format, parseISO, isValid } from 'date-fns';

interface SearchResultItem {
  id: string;
  title: string;
  typeLabel: string;
  icon: Component;
  date?: string;
  route: string;
}

const chatStore = useChatStore();
const projectStore = useProjectStore();
const uiStore = useUiStore();
const { t } = useI18n();

const model = defineModel<boolean>({ required: true });
const query = ref('');

const searchResultClass =
  'font-sans [&_.lucide]:!text-zinc-400 dark:[&_.lucide]:!text-zinc-500 [&_.menu-list-item-title]:!text-[0.9375rem] [&_.menu-list-item-title]:!font-medium [&_.menu-list-item-title]:!text-zinc-700 dark:[&_.menu-list-item-title]:!text-zinc-200 [&_.menu-list-item-subtitle]:!text-xs [&_.menu-list-item-subtitle]:!font-normal [&_.menu-list-item-subtitle]:!text-zinc-400 dark:[&_.menu-list-item-subtitle]:!text-zinc-500 [&_.menu-list-item-meta]:!font-normal [&_.menu-list-item-meta]:!text-zinc-400 dark:[&_.menu-list-item-meta]:!text-zinc-500';

watch(model, (open) => {
  if (open) {
    query.value = '';
  }
});

const projectResults = computed<SearchResultItem[]>(() =>
  projectStore.projects.map((p) => ({
    id: p.id,
    title: p.name,
    typeLabel: t('search.typeProject'),
    icon: FolderIcon,
    date: p.createdAt,
    route: `/projects/${p.id}`,
  })),
);

const chatResults = computed<SearchResultItem[]>(() =>
  chatStore.recentChats.map((c) => ({
    id: c.id,
    title: c.title,
    typeLabel: t('search.typeChat'),
    icon: HistoryIcon,
    date: c.createdAt,
    route: `/chat/${c.id}`,
  })),
);

const filteredProjects = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return projectResults.value;
  return projectResults.value.filter((item) => item.title.toLowerCase().includes(q));
});

const filteredChats = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return chatResults.value;
  return chatResults.value.filter((item) => item.title.toLowerCase().includes(q));
});

function toMenuItem(result: SearchResultItem): MenuItem {
  return {
    id: result.id,
    label: result.title,
    description: result.typeLabel,
    icon: result.icon,
    meta: result.date ? formatDate(result.date) : undefined,
    class: searchResultClass,
    onClick: () => onResultClick(result),
  };
}

const searchListEntries = computed<MenuEntry[]>(() => {
  const showSectionHeaders =
    filteredProjects.value.length > 0 && filteredChats.value.length > 0;
  const entries: MenuEntry[] = [];

  if (filteredProjects.value.length) {
    if (showSectionHeaders) {
      entries.push({ type: 'header', label: t('search.sectionProjects') });
    }
    entries.push(...filteredProjects.value.map(toMenuItem));
  }

  if (filteredChats.value.length) {
    if (showSectionHeaders) {
      entries.push({ type: 'header', label: t('search.sectionChats') });
    }
    entries.push(...filteredChats.value.map(toMenuItem));
  }

  return entries;
});

const emptyMessage = computed(() => {
  if (query.value.trim()) {
    return t('search.noResults');
  }
  return t('search.emptyHistory');
});

function onResultClick(item: SearchResultItem) {
  uiStore.closeMobileSidebar();
  model.value = false;
  navigateTo(item.route);
}

function formatDate(dateStr: string) {
  const date = parseISO(dateStr);
  if (!isValid(date)) return '';
  return format(date, 'MMM d');
}
</script>
