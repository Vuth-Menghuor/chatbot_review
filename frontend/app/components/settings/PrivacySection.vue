<template>
  <div class="space-y-6">
    <SettingsBlock spy-id="privacy-info" :title="$t('settings.privacy.infoTitle')">
      <div class="settings-panel">
        <div class="px-4 py-4">
          <p class="text-base leading-6 text-high-emphasis dark:text-zinc-100">
            {{ $t('settings.privacy.intro.beforeLinks') }}
            <a
              :href="$t('settings.privacy.links.privacyCenterUrl')"
              target="_blank"
              rel="noopener noreferrer"
              class="text-primary hover:underline"
            >
              {{ $t('settings.privacy.intro.privacyCenter') }}
            </a>
            {{ $t('settings.privacy.intro.betweenLinks') }}
            <a
              :href="$t('settings.privacy.links.privacyPolicyUrl')"
              target="_blank"
              rel="noopener noreferrer"
              class="text-primary hover:underline"
            >
              {{ $t('settings.privacy.intro.privacyPolicy') }}
            </a>
            {{ $t('settings.privacy.intro.afterLinks') }}
          </p>
        </div>

        <div class="border-t border-gray-100 dark:border-zinc-800">
          <a
            v-for="(link, index) in infoLinks"
            :key="link.labelKey"
            :href="link.url"
            target="_blank"
            rel="noopener noreferrer"
            class="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50 dark:hover:bg-zinc-800/50"
            :class="{ 'border-t border-gray-100 dark:border-zinc-800': index > 0 }"
          >
            <span class="text-base text-high-emphasis dark:text-zinc-100">{{ $t(link.labelKey) }}</span>
            <ChevronRightIcon class="h-4 w-4 shrink-0 text-medium-emphasis dark:text-zinc-400" aria-hidden="true" />
          </a>
        </div>
      </div>
    </SettingsBlock>

    <SettingsBlock spy-id="privacy-preferences" :title="$t('settings.privacy.preferencesTitle')">
      <SettingsSwitchList :items="preferenceItems" />
    </SettingsBlock>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { ChevronRightIcon } from 'lucide-vue-next';
import type { SettingsSwitchListItem } from '~/types/settings';
import { usePreferencesStore } from '~/stores/preferences.store';

const { t } = useI18n();
const preferencesStore = usePreferencesStore();

const infoLinks = computed(() => [
  {
    labelKey: 'settings.privacy.links.protectData',
    url: t('settings.privacy.links.protectDataUrl'),
  },
  {
    labelKey: 'settings.privacy.links.useData',
    url: t('settings.privacy.links.useDataUrl'),
  },
]);

const preferenceItems = computed<SettingsSwitchListItem[]>(() => [
  {
    key: 'locationMetadata',
    title: t('settings.privacy.items.locationMetadata.title'),
    description: t('settings.privacy.items.locationMetadata.description'),
    learnMoreUrl: t('settings.privacy.items.locationMetadata.learnMoreUrl'),
    learnMoreLabel: t('settings.privacy.items.locationMetadata.learnMore'),
    modelValue: preferencesStore.locationMetadata,
    onUpdate: preferencesStore.setLocationMetadata,
  },
  {
    key: 'helpImproveModel',
    title: t('settings.privacy.items.helpImproveModel.title'),
    description: t('settings.privacy.items.helpImproveModel.description'),
    learnMoreUrl: t('settings.privacy.items.helpImproveModel.learnMoreUrl'),
    learnMoreLabel: t('settings.privacy.items.helpImproveModel.learnMore'),
    modelValue: preferencesStore.helpImproveModel,
    onUpdate: preferencesStore.setHelpImproveModel,
  },
]);
</script>
