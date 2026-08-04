<template>
  <SettingsBlock spy-id="notifications" :title="$t('settings.notifications.title')">
    <div class="settings-panel">
      <template v-for="(id, index) in notificationIds" :key="id">
        <div class="flex items-start justify-between gap-3 px-4 py-3 sm:items-center sm:gap-4">
          <div class="min-w-0 flex-1">
            <p class="settings-item-title">
              {{ $t(`settings.notifications.items.${id}.title`) }}
            </p>
            <p class="settings-item-desc">
              {{ $t(`settings.notifications.items.${id}.description`) }}
            </p>
          </div>

          <BaseSwitch
            :model-value="isEnabled(id)"
            :aria-label="$t(`settings.notifications.items.${id}.title`)"
            @update:model-value="(value) => updateNotification(id, value)"
          />
        </div>

        <div
          v-if="index < notificationIds.length - 1"
          class="mx-4 border-t border-gray-100 dark:border-zinc-800"
        />
      </template>
    </div>
  </SettingsBlock>
</template>

<script setup lang="ts">
import {
  NOTIFICATION_IDS,
  type NotificationPreferenceId,
  useNotificationStore,
} from '~/stores/notification.store';

const { t } = useI18n();
const notificationStore = useNotificationStore();

const notificationIds = NOTIFICATION_IDS;

function isEnabled(id: NotificationPreferenceId) {
  return notificationStore.preferences[id] !== 'off';
}

function updateNotification(id: NotificationPreferenceId, value: boolean) {
  notificationStore.setNotificationEnabled(id, value);
  notificationStore.showToast({
    type: value ? 'success' : 'info',
    title: value
      ? t('settings.notifications.feedback.enabled')
      : t('settings.notifications.feedback.disabled'),
    message: t(`settings.notifications.items.${id}.title`),
  });

  if (id === 'sound' && value) {
    notificationStore.playNotificationSound();
  }
}
</script>
