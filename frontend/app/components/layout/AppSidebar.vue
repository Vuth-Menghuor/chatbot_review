<template>
  <aside
    ref="sidebarRef"
    class="z-102 flex h-screen flex-col overflow-visible bg-white pt-2 text-gray-700 transition-all duration-300 ease-in-out dark:bg-zinc-950 dark:text-zinc-300"
    :class="uiStore.sidebarClass(props.mode)"
    :style="uiStore.sidebarStyle(props.mode)"
  >
    <!-- Resize Handle (Only on Desktop & Expanded) -->
    <LayoutAppResizeHandle v-if="uiStore.showSidebarResizeHandle(props.mode)" />

    <div class="flex h-full flex-col bg-white text-base font-sans dark:bg-zinc-950">
      <!-- Logo & Toggle -->
      <div
        class="sticky top-0 z-10 flex h-14 items-center justify-between bg-white px-2.5 dark:bg-zinc-950"
      >
        <NuxtLink
          v-if="uiStore.showSidebarBrand(props.mode)"
          to="/"
          class="flex min-w-0 items-center gap-2 overflow-hidden transition-all px-1 no-underline"
        >
          <img src="/logo/gdce-new-seal.png" alt="GDCE Logo" class="w-10 h-10 object-contain" />
          <span class="ml-2 flex min-w-0 flex-col">
            <span
              class="truncate text-xl font-bold leading-none tracking-tight text-gray-900 dark:text-zinc-100"
            >
              {{ $t('sidebar.brand') }}
            </span>
          </span>
        </NuxtLink>

        <div
          v-if="uiStore.isSidebarDesktop(props.mode)"
          :class="uiStore.sidebarRailToggleWrapperClass(props.mode)"
        >
          <BaseIconButton
            :icon="uiStore.railMode ? PanelLeftOpenIcon : PanelLeftCloseIcon"
            :tooltip="$t('sidebar.toggleWidth')"
            custom-class="text-gray-800 transition-colors hover:bg-gray-200/50 hover:text-gray-700 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
            @click="uiStore.toggleRail"
          />
        </div>

        <!-- Mobile Close Button -->
        <BaseIconButton
          v-if="uiStore.isSidebarMobile(props.mode)"
          :icon="XIcon"
          size="small"
          custom-class="text-gray-400 hover:text-gray-600 dark:text-zinc-500 dark:hover:text-zinc-300"
          @click="uiStore.closeSidebar"
        />
      </div>

      <!-- Search + New Chat -->
      <div
        :class="
          uiStore.isSidebarRail(props.mode)
            ? 'mt-1 flex flex-col items-center'
            : 'mt-1 mb-0.5 px-2.5'
        "
      >
        <BaseActionRow
          :rail="uiStore.isSidebarRail(props.mode)"
          :icon="SquarePenIcon"
          :label="$t('sidebar.newChat')"
          @click="onCreateChat"
        />
        <BaseActionRow
          :rail="uiStore.isSidebarRail(props.mode)"
          :icon="SearchIcon"
          :label="$t('sidebar.searchPlaceholder')"
          :tooltip="$t('sidebar.search')"
          @click="uiStore.openSearchDialog()"
        />
      </div>

      <!-- Main Navigation -->
      <div class="flex-1 overflow-y-auto px-0.5 custom-scrollbar">
        <SidebarProjects :rail="uiStore.isSidebarRail(props.mode)" @create="createProjectOpen = true" />
        <SidebarRecents :rail="uiStore.isSidebarRail(props.mode)" />
      </div>

      <!-- Footer: profile trigger → user menu -->
      <SidebarUserMenu
        :mode="props.mode"
        class="mt-auto w-full shrink-0 border-t border-gray-200/50 dark:border-zinc-800"
      />
    </div>

    <!-- Dialogs -->
    <SidebarSearchDialog v-model="searchDialogOpen" />
    <SidebarCreateProjectDialog v-model="createProjectOpen" @create="onCreateProject" />
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useUiStore, type SidebarMode } from '~/stores/ui.store';
import { PanelLeftCloseIcon, PanelLeftOpenIcon, XIcon, SquarePenIcon, SearchIcon } from 'lucide-vue-next';
import { navigateTo } from '#imports';
import { useProjects } from '~/composables/useProjects';
import SidebarUserMenu from '~/components/sidebar/SidebarUserMenu.vue';

const props = withDefaults(
  defineProps<{
    mode?: SidebarMode;
  }>(),
  {
    mode: 'desktop',
  },
);

const uiStore = useUiStore();
const { createProject } = useProjects();
const { searchDialogOpen } = storeToRefs(uiStore);

const createProjectOpen = ref(false);

function onCreateChat() {
  uiStore.closeMobileSidebar();
  navigateTo('/');
}

async function onCreateProject(name: string, category: string) {
  const project = await createProject(name, category);
  createProjectOpen.value = false;
  navigateTo(`/projects/${project.id}`);
}

</script>
