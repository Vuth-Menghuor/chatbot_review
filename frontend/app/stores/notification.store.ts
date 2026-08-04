import { defineStore } from 'pinia';
import { ref } from 'vue';
import { readJson, readString, storageKeys, writeJson, writeString } from '~/utils/storage';

const RESPONSE_COMPLETED_ID = 'responseCompleted';
const ENABLED_CHANNEL: NotificationChannel = 'push';
const DISABLED_CHANNEL: NotificationChannel = 'off';
const DEFAULT_TOAST_DURATION_MS = 3200;
const NOTIFICATION_SOUND = {
  type: 'sine' as OscillatorType,
  frequency: 740,
  volume: 0.04,
  durationSeconds: 0.08,
};

type ToastType = 'success' | 'info' | 'error';

export type NotificationChannel = 'push' | 'email' | 'off';

export type NotificationPreferenceId =
  | 'responseCompleted'
  | 'projects'
  | 'tasks'
  | 'newMessages'
  | 'sound';

export type NotificationPreferences = Record<NotificationPreferenceId, NotificationChannel>;

export const NOTIFICATION_IDS: NotificationPreferenceId[] = [
  RESPONSE_COMPLETED_ID,
  'projects',
  'tasks',
  'newMessages',
  'sound',
];

export type AppToast = {
  id: string;
  title: string;
  message?: string;
  type: ToastType;
  notificationId?: NotificationPreferenceId;
};

export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  responseCompleted: ENABLED_CHANNEL,
  projects: 'email',
  tasks: ENABLED_CHANNEL,
  newMessages: ENABLED_CHANNEL,
  sound: ENABLED_CHANNEL,
};

export const useNotificationStore = defineStore('notification', () => {
  const preferences = ref<NotificationPreferences>({ ...DEFAULT_NOTIFICATION_PREFERENCES });
  const toasts = ref<AppToast[]>([]);
  let toastId = 0;

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
        responseCompleted: legacy === 'true' ? ENABLED_CHANNEL : DISABLED_CHANNEL,
      };
      persistPreferences();
    }
  }

  function setNotificationChannel(id: NotificationPreferenceId, channel: NotificationChannel) {
    preferences.value = { ...preferences.value, [id]: channel };
    persistPreferences();

    if (id === RESPONSE_COMPLETED_ID) {
      writeString(storageKeys.responseCompletionToast, String(channel === ENABLED_CHANNEL));
    }
  }

  function setNotificationEnabled(id: NotificationPreferenceId, enabled: boolean) {
    if (!enabled) {
      setNotificationChannel(id, DISABLED_CHANNEL);
      return;
    }

    const channel =
      preferences.value[id] === DISABLED_CHANNEL ? ENABLED_CHANNEL : preferences.value[id];
    setNotificationChannel(id, channel);
  }

  function playNotificationSound() {
    if (!import.meta.client || preferences.value.sound === 'off') return;

    try {
      const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextCtor) return;

      const audioContext = new AudioContextCtor();
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();

      oscillator.type = NOTIFICATION_SOUND.type;
      oscillator.frequency.value = NOTIFICATION_SOUND.frequency;
      gain.gain.value = NOTIFICATION_SOUND.volume;
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start();
      oscillator.stop(audioContext.currentTime + NOTIFICATION_SOUND.durationSeconds);
    } catch {
      // Ignore browsers that block audio until a stronger user gesture.
    }
  }

  function resetNotificationPreferences() {
    preferences.value = { ...DEFAULT_NOTIFICATION_PREFERENCES };
    persistPreferences();
    writeString(
      storageKeys.responseCompletionToast,
      String(DEFAULT_NOTIFICATION_PREFERENCES.responseCompleted === ENABLED_CHANNEL),
    );
  }

  function removeToast(id: string) {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  function showToast(toast: Omit<AppToast, 'id'>, duration = DEFAULT_TOAST_DURATION_MS) {
    if (toast.notificationId && preferences.value[toast.notificationId] === DISABLED_CHANNEL) {
      return;
    }

    const id = `toast-${Date.now()}-${toastId++}`;
    toasts.value = [...toasts.value, { id, ...toast }];
    if (toast.notificationId) playNotificationSound();

    if (import.meta.client) {
      window.setTimeout(() => removeToast(id), duration);
    }
  }

  return {
    preferences,
    toasts,
    init,
    setNotificationEnabled,
    resetNotificationPreferences,
    showToast,
    playNotificationSound,
    removeToast,
  };
});
