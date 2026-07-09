<template>
  <div class="settings-panel">
    <template v-for="(item, index) in items" :key="item.key">
      <div class="flex items-start justify-between gap-3 px-4 py-3 sm:items-center sm:gap-4">
        <div class="min-w-0 flex-1">
          <p class="settings-item-title">{{ item.title }}</p>
          <p class="settings-item-desc">
            {{ item.description }}
            <template v-if="item.learnMoreUrl">
              {{ ' ' }}
              <a
                :href="item.learnMoreUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="text-primary hover:underline"
              >
                {{ item.learnMoreLabel }}
              </a>
            </template>
          </p>
        </div>

        <BaseSwitch
          :model-value="item.modelValue"
          :aria-label="item.title"
          @update:model-value="item.onUpdate"
        />
      </div>

      <div
        v-if="index < items.length - 1"
        class="mx-4 border-t border-gray-100 dark:border-zinc-800"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { SettingsSwitchListItem } from '~/types/settings';

defineProps<{
  items: SettingsSwitchListItem[];
}>();
</script>
