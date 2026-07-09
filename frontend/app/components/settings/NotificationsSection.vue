<template>
  <SettingsBlock spy-id="notifications" :title="$t('settings.notifications.title')">
    <SettingsSwitchList :items="switchItems" />
  </SettingsBlock>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import type { SettingsSwitchListItem } from '~/types/settings';
import type { NotificationPreferenceId } from '~/stores/notification.store';
import { useNotificationStore } from '~/stores/notification.store';

const { t } = useI18n();
const notificationStore = useNotificationStore();

const notificationIds: NotificationPreferenceId[] = [
  'responseCompleted',
  'projects',
  'tasks',
  'newMessages',
];

const switchItems = computed<SettingsSwitchListItem[]>(() =>
  notificationIds.map((id) => ({
    key: id,
    title: t(`settings.notifications.items.${id}.title`),
    description: t(`settings.notifications.items.${id}.description`),
    modelValue: notificationStore.isNotificationEnabled(id),
    onUpdate: (value) => notificationStore.setNotificationEnabled(id, value),
  })),
);
</script>
