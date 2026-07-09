import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { readJson, readString, storageKeys, writeJson, writeString } from '~/utils/storage';

type ToastType = 'success' | 'info';

export type NotificationChannel = 'push' | 'email' | 'off';

export type NotificationPreferenceId =
  | 'responseCompleted'
  | 'projects'
  | 'tasks'
  | 'newMessages';

export type NotificationPreferences = Record<NotificationPreferenceId, NotificationChannel>;

export type AppToast = {
  id: string;
  title: string;
  message?: string;
  type: ToastType;
};

export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  responseCompleted: 'push',
  projects: 'email',
  tasks: 'push',
  newMessages: 'push',
};

export const useNotificationStore = defineStore('notification', () => {
  const preferences = ref<NotificationPreferences>({ ...DEFAULT_NOTIFICATION_PREFERENCES });
  const toasts = ref<AppToast[]>([]);
  let toastId = 0;

  const responseCompletionToast = computed(
    () => preferences.value.responseCompleted === 'push',
  );

  function persistPreferences() {
    writeJson(storageKeys.notificationPreferences, preferences.value);
  }

  function init() {
    const hasSavedPrefs =
      import.meta.client && localStorage.getItem(storageKeys.notificationPreferences) !== null;

    if (hasSavedPrefs) {
      const savedPrefs = readJson(
        storageKeys.notificationPreferences,
        DEFAULT_NOTIFICATION_PREFERENCES,
      );
      preferences.value = { ...DEFAULT_NOTIFICATION_PREFERENCES, ...savedPrefs };
      return;
    }

    const legacy = readString(storageKeys.responseCompletionToast);
    if (legacy !== null) {
      preferences.value = {
        ...DEFAULT_NOTIFICATION_PREFERENCES,
        responseCompleted: legacy === 'true' ? 'push' : 'off',
      };
      persistPreferences();
    }
  }

  function getChannel(id: NotificationPreferenceId): NotificationChannel {
    return preferences.value[id];
  }

  function setNotificationChannel(id: NotificationPreferenceId, channel: NotificationChannel) {
    preferences.value = { ...preferences.value, [id]: channel };
    persistPreferences();

    if (id === 'responseCompleted') {
      writeString(storageKeys.responseCompletionToast, String(channel === 'push'));
    }
  }

  function isNotificationEnabled(id: NotificationPreferenceId): boolean {
    return preferences.value[id] !== 'off';
  }

  function setNotificationEnabled(id: NotificationPreferenceId, enabled: boolean) {
    if (!enabled) {
      setNotificationChannel(id, 'off');
      return;
    }

    const channel = preferences.value[id] === 'off' ? 'push' : preferences.value[id];
    setNotificationChannel(id, channel);
  }

  function setResponseCompletionToast(value: boolean) {
    setNotificationChannel('responseCompleted', value ? 'push' : 'off');
  }

  function resetNotificationPreferences() {
    preferences.value = { ...DEFAULT_NOTIFICATION_PREFERENCES };
    persistPreferences();
    writeString(
      storageKeys.responseCompletionToast,
      String(DEFAULT_NOTIFICATION_PREFERENCES.responseCompleted === 'push'),
    );
  }

  function shouldShowResponseCompletionToast(): boolean {
    return preferences.value.responseCompleted === 'push';
  }

  function removeToast(id: string) {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  function showToast(toast: Omit<AppToast, 'id'>, duration = 3200) {
    const id = `toast-${Date.now()}-${toastId++}`;
    toasts.value = [...toasts.value, { id, ...toast }];

    if (import.meta.client) {
      window.setTimeout(() => removeToast(id), duration);
    }
  }

  return {
    preferences,
    responseCompletionToast,
    toasts,
    init,
    getChannel,
    setNotificationChannel,
    isNotificationEnabled,
    setNotificationEnabled,
    setResponseCompletionToast,
    resetNotificationPreferences,
    shouldShowResponseCompletionToast,
    showToast,
    removeToast,
  };
});
