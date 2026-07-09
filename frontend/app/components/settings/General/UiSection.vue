<template>
  <SettingsBlock spy-id="ui" :title="$t('settings.ui.title')">
    <SettingsSwitchList :items="sidebarRailItems" />

    <div class="space-y-3 pt-3">
      <h3 class="settings-section-title px-1">{{ $t('settings.ui.fontSize.title') }}</h3>
      <div class="settings-panel">
        <div
          class="grid grid-cols-3 gap-1 bg-gray-50 p-1 dark:bg-zinc-900/70"
          role="radiogroup"
          :aria-label="$t('settings.ui.fontSize.title')"
        >
          <BaseButton
            v-for="option in fontSizeOptions"
            :key="option.value"
            type="button"
            role="radio"
            variant="text"
            size="small"
            block
            :aria-checked="preferencesStore.fontSize === option.value"
            :custom-class="
              preferencesStore.fontSize === option.value
                ? 'h-8 min-w-0 bg-white px-2 text-sm font-semibold text-gray-950 shadow-sm ring-1 ring-gray-200 [&_.v-btn__overlay]:!opacity-0 dark:bg-zinc-800 dark:text-zinc-100 dark:ring-zinc-700'
                : 'h-8 min-w-0 px-2 text-sm text-gray-600 [&_.v-btn__overlay]:!opacity-0 hover:bg-white/70 hover:text-gray-950 dark:text-zinc-400 dark:hover:bg-zinc-800/70 dark:hover:text-zinc-100'
            "
            @click="preferencesStore.setFontSize(option.value)"
          >
            <span class="truncate">{{ option.label }}</span>
          </BaseButton>
        </div>
      </div>
    </div>
  </SettingsBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { SettingsSwitchListItem } from '~/types/settings';
import { usePreferencesStore, type FontSizePreference } from '~/stores/preferences.store';
import { useUiStore } from '~/stores/ui.store';
import { writeString, storageKeys } from '~/utils/storage';

const { t } = useI18n();
const preferencesStore = usePreferencesStore();
const uiStore = useUiStore();

const fontSizeOptions = computed(() => [
  { value: 'small' as FontSizePreference, label: t('settings.ui.fontSize.small') },
  { value: 'medium' as FontSizePreference, label: t('settings.ui.fontSize.medium') },
  { value: 'large' as FontSizePreference, label: t('settings.ui.fontSize.large') },
]);

const sidebarRailItems = computed<SettingsSwitchListItem[]>(() => [
  {
    key: 'defaultSidebarRail',
    title: t('settings.ui.defaultSidebarRail.title'),
    description: t('settings.ui.defaultSidebarRail.description'),
    modelValue: preferencesStore.defaultSidebarRail,
    onUpdate: (value) => {
      preferencesStore.setDefaultSidebarRail(value);
      if (value) {
        uiStore.railMode = true;
        writeString(storageKeys.railMode, 'true');
      }
    },
  },
]);
</script>
