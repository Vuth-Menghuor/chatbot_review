<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute, definePageMeta, navigateTo } from '#imports';
import { FolderIcon, PlusIcon } from 'lucide-vue-next';
import { useUiStore } from '~/stores/ui.store';
import { useProjectStore } from '~/stores/project.store';
import { useChatActions } from '~/composables/useChat';
import { useChatStore } from '~/stores/chat.store';
import { storeToRefs } from 'pinia';
import BaseTabs from '~/components/base/BaseTabs.vue';

interface Source {
  name: string;
  type: string;
  color: string;
}

definePageMeta({
  layout: 'default',
});

const route = useRoute();
const uiStore = useUiStore();
const rawProjectParam = route.params.id;
const projectId = (Array.isArray(rawProjectParam) ? rawProjectParam[0] : rawProjectParam) as string;
const chatStore = useChatStore();
const { t } = useI18n();

const TAB_CHATS = 'Chats';
const TAB_SOURCES = 'Sources';
const activeTab = ref(TAB_CHATS);
const projectSourcesRef = ref<{ triggerUpload: () => void } | null>(null);
const sourceList = ref<Source[]>([]);
const projectStore = useProjectStore();
const { projects } = storeToRefs(projectStore);
const { sortedChats } = useChatActions();
const project = computed(() => {
  return projects.value.find((p) => p.id === projectId);
});

const projectName = computed(() => {
  return project.value ? project.value.name : t('project.defaultTitle');
});

const projectTabs = computed(() => [
  { title: t('project.tabs.chats'), value: TAB_CHATS },
  { title: t('project.tabs.sources'), value: TAB_SOURCES },
]);

const projectChats = computed(() => {
  return sortedChats.value.filter((c) => c.projectId === projectId);
});

/** Home (`/`) composer UX; chat stays under this project via `projectId` or `?project=` on index. */
function goToProjectHomeChat() {
  void navigateTo({ path: '/', query: { project: projectId } });
}

function handleNewChat({
  text,
  onResult,
}: {
  text: string;
  files?: File[];
  onResult?: (accepted: boolean) => void;
}) {
  const trimmed = text.trim();
  if (!trimmed) {
    goToProjectHomeChat();
    onResult?.(true);
    return;
  }
  const chat = chatStore.createChat(t('chat.newChat'), projectId);
  onResult?.(true);
  void navigateTo(`/chat/${chat.id}?q=${encodeURIComponent(trimmed)}`);
}

function triggerSourceUpload() {
  projectSourcesRef.value?.triggerUpload();
}

function onChatClick(id: string) {
  uiStore.closeMobileSidebar();
  navigateTo(`/chat/${id}`);
}
</script>

<template>
  <div class="flex h-full flex-col bg-white dark:bg-zinc-950">
    <LayoutAppContainer>
      <div class="flex flex-col h-full px-1 sm:px-4 py-6 md:py-8">
        <!-- Chat Input Field (Standalone) -->
        <div class="mb-7">
          <ChatInput :docked="false" @send="handleNewChat" />
        </div>

        <!-- Content Selection Tabs & Action Header -->
        <div
          class="mb-5 flex items-center justify-between gap-3 border-b border-gray-200/80 dark:border-zinc-800"
        >
          <BaseTabs v-model="activeTab" :items="projectTabs" variant="underline" />

          <div class="flex items-center gap-2 pb-2">
            <BaseButton
              variant="tonal"
              size="small"
              custom-class="project-action bg-orange-500/10 text-orange-600 hover:bg-orange-500/15 dark:bg-orange-400/10 dark:text-orange-400 dark:hover:bg-orange-400/15"
              @click="activeTab === TAB_CHATS ? goToProjectHomeChat() : triggerSourceUpload()"
            >
              <PlusIcon :size="15" class="mr-1.5" />
              {{ activeTab === TAB_CHATS ? $t('sidebar.newChat') : $t('project.newSource') }}
            </BaseButton>
          </div>
        </div>

        <!-- Tab Content -->
        <v-window v-model="activeTab" class="flex-1 overflow-hidden bg-white dark:bg-zinc-950">
          <v-window-item value="Chats" class="h-full">
            <ProjectChat
              :chat-list="projectChats"
              @chat-click="onChatClick"
              @new-chat="goToProjectHomeChat"
            />
          </v-window-item>

          <v-window-item value="Sources" class="h-full">
            <ProjectSources
              ref="projectSourcesRef"
              :source-list="sourceList"
              @add-source="(source) => sourceList.push(source)"
              @remove-source="(index: number) => sourceList.splice(index, 1)"
            />
          </v-window-item>
        </v-window>
      </div>
    </LayoutAppContainer>
  </div>
</template>

<style scoped>
:deep(.v-tab) {
  opacity: 1 !important;
}

:deep(.v-tab--selected) {
  opacity: 1 !important;
}

:deep(.project-tab-active) {
  color: #f97316 !important;
}

:global(.dark) :deep(.project-tab-active) {
  color: #fb923c !important;
}

/* REMOVE VUETIFY OVERLAY */
:deep(.v-tab__overlay) {
  opacity: 0 !important;
  background: transparent !important;
}

/* REMOVE ACTIVE DARK BG */
:deep(.v-btn__overlay) {
  opacity: 0 !important;
}

:deep(.v-ripple__container) {
  opacity: 0 !important;
}
</style>
