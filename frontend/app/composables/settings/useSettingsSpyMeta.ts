import { computed } from 'vue';

export interface SettingsSpyHeader {
  title: string;
  description: string;
}

export function useSettingsSpyMeta() {
  const { t } = useI18n();

  const spyHeaders = computed<Record<string, SettingsSpyHeader>>(() => ({
    appearance: {
      title: t('settings.appearance.title'),
      description: t('settings.appearance.description'),
    },
    language: {
      title: t('settings.language.title'),
      description: t('settings.language.description'),
    },
    chat: {
      title: t('settings.chat.title'),
      description: t('settings.chat.description'),
    },
    ui: {
      title: t('settings.ui.title'),
      description: t('settings.ui.description'),
    },
    notifications: {
      title: t('settings.notifications.title'),
      description: t('settings.notifications.description'),
    },
    'account-details': {
      title: t('settings.account.detailsTitle'),
      description: t('settings.account.detailsDescription'),
    },
    privacy: {
      title: t('settings.privacy.title'),
      description: t('settings.privacy.description'),
    },
    'privacy-info': {
      title: t('settings.privacy.infoTitle'),
      description: t('settings.privacy.description'),
    },
    'privacy-preferences': {
      title: t('settings.privacy.preferencesTitle'),
      description: t('settings.privacy.description'),
    },
    'keyboard-composer': {
      title: t('settings.keyboard.groups.composer'),
      description: t('settings.keyboard.description'),
    },
    'keyboard-navigation': {
      title: t('settings.keyboard.groups.navigation'),
      description: t('settings.keyboard.description'),
    },
    'keyboard-settings': {
      title: t('settings.keyboard.groups.settings'),
      description: t('settings.keyboard.description'),
    },
    'keyboard-general': {
      title: t('settings.keyboard.groups.general'),
      description: t('settings.keyboard.description'),
    },
  }));

  return { spyHeaders };
}
