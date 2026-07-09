<template>
  <div>
    <Transition name="fade">
      <div
        v-if="uiStore.sidebarOpened"
        class="fixed inset-0 z-101 bg-black/50 md:hidden"
        @click="uiStore.closeSidebar"
      />
    </Transition>

    <div
      class="fixed top-0 left-0 z-102 h-screen transition-transform duration-300 ease-in-out md:hidden"
      :class="uiStore.sidebarOpened ? 'translate-x-0' : '-translate-x-full'"
    >
      <LayoutAppSidebar mode="mobile" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUiStore } from '~/stores/ui.store';
const uiStore = useUiStore();
</script>
