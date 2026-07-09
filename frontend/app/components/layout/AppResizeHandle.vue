<template>
  <div
    class="sidebar-resize-handle group absolute top-0 -right-1 z-50 h-full w-2 cursor-col-resize transition-colors"
    :class="{ 'is-dragging': uiStore.isDragging, 'hover:bg-blue-400/30': !uiStore.railMode }"
    @mousedown="startDragging"
    @touchstart="startDragging"
  >
    <div
      class="pointer-events-none absolute top-0 right-1 h-full w-[2px] bg-transparent transition-colors group-hover:bg-blue-500/50"
      :class="{ 'bg-blue-500': uiStore.isDragging }"
    />
  </div>
</template>

<script setup lang="ts">
import { onUnmounted } from 'vue';
import { useUiStore } from '~/stores/ui.store';

const uiStore = useUiStore();

const startDragging = (e: MouseEvent | TouchEvent) => {
  if (e instanceof MouseEvent && e.button !== 0) return;

  if (e.cancelable) e.preventDefault();

  uiStore.isDragging = true;
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', stopDragging);
  document.addEventListener('touchmove', onMouseMove, { passive: false });
  document.addEventListener('touchend', stopDragging);
  document.body.style.cursor = 'col-resize';
  document.body.style.userSelect = 'none';
};

const onMouseMove = (e: MouseEvent | TouchEvent) => {
  if (!uiStore.isDragging) return;

  const clientX = e instanceof MouseEvent ? e.clientX : e.touches[0]?.clientX;
  if (clientX !== undefined) {
    uiStore.setSidebarWidth(clientX);
  }
};

const stopDragging = () => {
  uiStore.isDragging = false;
  document.removeEventListener('mousemove', onMouseMove);
  document.removeEventListener('mouseup', stopDragging);
  document.removeEventListener('touchmove', onMouseMove);
  document.removeEventListener('touchend', stopDragging);
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
};

onUnmounted(() => {
  stopDragging();
});
</script>
