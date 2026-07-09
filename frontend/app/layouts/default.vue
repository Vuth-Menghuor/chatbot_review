<template>
  <div
    class="flex h-screen min-h-0 overflow-hidden bg-muted100 font-sans selection:bg-blue-100 dark:selection:bg-blue-900/40"
    :class="{ 'no-transition': uiStore.isDragging }"
  >
    <LayoutAppDrawer />
    <LayoutAppSidebar />
    <LayoutAppToastHost />
    <SettingsDialog />
    <v-main class="flex! min-h-0! min-w-0! flex-1 flex-col overflow-hidden p-0!">
      <div class="flex h-full min-h-0 min-w-0 flex-1 overflow-hidden">
        <!-- Main Column (Chat/Page Content) -->
        <div class="flex min-h-0 min-w-0 flex-1 flex-col bg-surface">
          <LayoutAppHeader />
          <div class="flex min-h-0 flex-1 flex-col overflow-hidden">
            <slot />
          </div>
        </div>
        <!-- Right Panel: Files -->
        <LayoutAppFilesPanel />
      </div>
    </v-main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue';
import { useAppKeyboardShortcuts } from '~/composables/keyboard/useAppKeyboardShortcuts';
import { useNotificationStore } from '~/stores/notification.store';
import { usePreferencesStore } from '~/stores/preferences.store';
import { useUiStore } from '~/stores/ui.store';
import SettingsDialog from '~/components/settings/SettingsDialog.vue';

const uiStore = useUiStore();
const notificationStore = useNotificationStore();
const preferencesStore = usePreferencesStore();

useAppKeyboardShortcuts();

onMounted(() => {
  preferencesStore.init();
  uiStore.init();
  notificationStore.init();
});
</script>
