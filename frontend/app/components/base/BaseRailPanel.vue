<template>
  <div class="flex justify-center transition-transform duration-300">
    <v-menu location="right" :offset="offset" transition="slide-x-transition">
      <template #activator="{ props: menuProps }">
        <BaseIconButton
          v-bind="menuProps"
          :icon="icon"
          variant="text"
          :tooltip="tooltip"
          tooltip-location="right"
          :custom-class="activatorClass"
        />
      </template>

      <v-card
        :width="width"
        color="surface"
        class="overflow-hidden rounded-lg border border-opacity-25 py-2 shadow-lg"
      >
        <div
          class="mb-1 border-b border-opacity-25 px-4 py-2 text-xs font-bold tracking-wider text-medium-emphasis uppercase"
        >
          {{ title }}
        </div>
        <div class="custom-scrollbar flex max-h-[400px] flex-col gap-0.5 overflow-y-auto px-1">
          <BaseMenuList tone="nav" bg-color="transparent" list-class="pa-0">
            <slot />
          </BaseMenuList>

          <template v-if="$slots.footer">
            <v-divider class="my-1 opacity-50" />
            <BaseMenuList tone="nav" bg-color="transparent" list-class="pa-0">
              <slot name="footer" />
            </BaseMenuList>
          </template>
        </div>
      </v-card>
    </v-menu>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue';
withDefaults(
  defineProps<{
    icon: Component;
    tooltip: string;
    title: string;
    width?: string | number;
    offset?: number | string;
    activatorClass?: string;
  }>(),
  {
    width: 220,
    offset: 12,
    activatorClass:
      'h-10 w-10 min-w-0 border-0 text-gray-800 hover:bg-gray-200/50 dark:text-zinc-300 dark:hover:bg-zinc-800',
  },
);
</script>
