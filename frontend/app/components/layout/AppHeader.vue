<template>
  <div
    class="h-14 border-b border-gray-100 dark:border-zinc-800 bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md shrink-0 px-2 sm:px-4 flex items-center justify-between z-40"
  >
    <div class="flex items-center w-full">
      <!-- Mobile Toggle -->
      <BaseIconButton
        custom-class="md:hidden text-gray-800 dark:text-zinc-200"
        @click="uiStore.openSidebar"
      >
        <ChartNoAxesColumnIcon class="w-5 h-5 rotate-90" />
      </BaseIconButton>
      <NavbarChatTitle />

      <v-spacer />

      <div class="flex items-center gap-1 sm:gap-2">
        <!-- New Chat (Mobile Only) -->
        <BaseIconButton
          :icon="SquarePenIcon"
          width="36"
          height="36"
          custom-class="md:hidden text-gray-700 dark:text-zinc-200"
          :tooltip="$t('chat.newChat')"
          @click="onCreateChat"
        />

        <!-- Chat Actions (Desktop & Mobile when in a chat session) -->
        <template v-if="isChatPage && !isSettingsPage">
          <!-- Share Button (Desktop Only) -->
          <BaseButton
            variant="text"
            custom-class="hidden md:flex bg-white dark:bg-zinc-800 border-none dark:border-zinc-700 text-base hover:bg-gray-50 dark:hover:bg-zinc-700 font-medium h-9 transition-all px-3 mr-1"
            @click="shareDialogOpen = true"
          >
            <UploadIcon class="w-4 h-4 mr-2" />
            <span class="text-base">{{ $t('common.share') }}</span>
          </BaseButton>

          <!-- More Menu (Mobile: has share inside | Desktop: share is separate) -->
          <NavbarChatMoreMenu @share="shareDialogOpen = true" />
        </template>
      </div>
    </div>
  </div>

  <NavbarChatShareDialog v-model="shareDialogOpen" />
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { ChartNoAxesColumnIcon, SquarePenIcon, UploadIcon } from 'lucide-vue-next';
import { useUiStore } from '~/stores/ui.store';
import { navigateTo } from '#imports';
import { useNavbarRouteContext } from '~/composables/navbar/useRouteContext';

const uiStore = useUiStore();
const { isChatPage, isSettingsPage } = useNavbarRouteContext();
const shareDialogOpen = ref(false);

function onCreateChat() {
  uiStore.closeMobileSidebar();
  navigateTo('/');
}
</script>
