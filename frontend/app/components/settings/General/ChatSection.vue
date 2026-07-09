<template>
  <SettingsBlock :spy-id="'chat'" :title="$t('settings.chat.title')">
    <SettingsSwitchList :items="switchItems" />
  </SettingsBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { SettingsSwitchListItem } from '~/types/settings';
import { usePreferencesStore } from '~/stores/preferences.store';

const { t } = useI18n();
const preferencesStore = usePreferencesStore();

const switchItems = computed<SettingsSwitchListItem[]>(() => [
  {
    key: 'enterToSend',
    title: t('settings.chat.enterToSend.title'),
    description: t('settings.chat.enterToSend.description'),
    modelValue: preferencesStore.enterToSend,
    onUpdate: preferencesStore.setEnterToSend,
  },
  {
    key: 'autoScroll',
    title: t('settings.chat.autoScroll.title'),
    description: t('settings.chat.autoScroll.description'),
    modelValue: preferencesStore.autoScrollMessages,
    onUpdate: preferencesStore.setAutoScrollMessages,
  },
]);
</script>
