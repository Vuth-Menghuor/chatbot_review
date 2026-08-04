import { defineStore } from 'pinia';
import { ref } from 'vue';
import { readJson, storageKeys, writeJson } from '~/utils/storage';

export type FontSizePreference = 'small' | 'medium' | 'large';
export type FontStylePreference = 'system' | 'serif' | 'mono';

export interface ChatPreferences {
  enterToSend: boolean;
  autoScrollMessages: boolean;
}

export interface UiPreferences {
  defaultSidebarRail: boolean;
  fontSize: FontSizePreference;
  fontStyle: FontStylePreference;
}

export interface PrivacyPreferences {
  locationMetadata: boolean;
  helpImproveModel: boolean;
  publicChatSharing: boolean;
  showChatHistory: boolean;
}

export const DEFAULT_CHAT_PREFERENCES: ChatPreferences = {
  enterToSend: true,
  autoScrollMessages: true,
};

export const DEFAULT_UI_PREFERENCES: UiPreferences = {
  defaultSidebarRail: false,
  fontSize: 'medium',
  fontStyle: 'system',
};

export const DEFAULT_PRIVACY_PREFERENCES: PrivacyPreferences = {
  locationMetadata: true,
  helpImproveModel: true,
  publicChatSharing: false,
  showChatHistory: true,
};

let initialized = false;

export const usePreferencesStore = defineStore('preferences', () => {
  const enterToSend = ref(DEFAULT_CHAT_PREFERENCES.enterToSend);
  const autoScrollMessages = ref(DEFAULT_CHAT_PREFERENCES.autoScrollMessages);
  const defaultSidebarRail = ref(DEFAULT_UI_PREFERENCES.defaultSidebarRail);
  const fontSize = ref<FontSizePreference>(DEFAULT_UI_PREFERENCES.fontSize);
  const fontStyle = ref<FontStylePreference>(DEFAULT_UI_PREFERENCES.fontStyle);
  const locationMetadata = ref(DEFAULT_PRIVACY_PREFERENCES.locationMetadata);
  const helpImproveModel = ref(DEFAULT_PRIVACY_PREFERENCES.helpImproveModel);
  const publicChatSharing = ref(DEFAULT_PRIVACY_PREFERENCES.publicChatSharing);
  const showChatHistory = ref(DEFAULT_PRIVACY_PREFERENCES.showChatHistory);

  function persistChat() {
    writeJson(storageKeys.chatPreferences, {
      enterToSend: enterToSend.value,
      autoScrollMessages: autoScrollMessages.value,
    });
  }

  function persistUi() {
    writeJson(storageKeys.uiPreferences, {
      defaultSidebarRail: defaultSidebarRail.value,
      fontSize: fontSize.value,
      fontStyle: fontStyle.value,
    });
  }

  function persistPrivacy() {
    writeJson(storageKeys.privacyPreferences, {
      locationMetadata: locationMetadata.value,
      helpImproveModel: helpImproveModel.value,
      publicChatSharing: publicChatSharing.value,
      showChatHistory: showChatHistory.value,
    });
  }

  function init() {
    if (!import.meta.client || initialized) return;
    initialized = true;

    const chat = readJson(storageKeys.chatPreferences, DEFAULT_CHAT_PREFERENCES);
    const ui = readJson(storageKeys.uiPreferences, DEFAULT_UI_PREFERENCES);
    const privacy = readJson(storageKeys.privacyPreferences, DEFAULT_PRIVACY_PREFERENCES);

    enterToSend.value = chat.enterToSend ?? DEFAULT_CHAT_PREFERENCES.enterToSend;
    autoScrollMessages.value =
      chat.autoScrollMessages ?? DEFAULT_CHAT_PREFERENCES.autoScrollMessages;
    defaultSidebarRail.value =
      ui.defaultSidebarRail ?? DEFAULT_UI_PREFERENCES.defaultSidebarRail;
    fontSize.value = ui.fontSize ?? DEFAULT_UI_PREFERENCES.fontSize;
    fontStyle.value = ui.fontStyle ?? DEFAULT_UI_PREFERENCES.fontStyle;
    locationMetadata.value =
      privacy.locationMetadata ?? DEFAULT_PRIVACY_PREFERENCES.locationMetadata;
    helpImproveModel.value =
      privacy.helpImproveModel ?? DEFAULT_PRIVACY_PREFERENCES.helpImproveModel;
    publicChatSharing.value =
      privacy.publicChatSharing ?? DEFAULT_PRIVACY_PREFERENCES.publicChatSharing;
    showChatHistory.value =
      privacy.showChatHistory ?? DEFAULT_PRIVACY_PREFERENCES.showChatHistory;
  }

  function setEnterToSend(value: boolean) {
    enterToSend.value = value;
    persistChat();
  }

  function setAutoScrollMessages(value: boolean) {
    autoScrollMessages.value = value;
    persistChat();
  }

  function setDefaultSidebarRail(value: boolean) {
    defaultSidebarRail.value = value;
    persistUi();
  }

  function setFontSize(value: FontSizePreference) {
    fontSize.value = value;
    persistUi();
  }

  function setFontStyle(value: FontStylePreference) {
    fontStyle.value = value;
    persistUi();
  }

  function setLocationMetadata(value: boolean) {
    locationMetadata.value = value;
    persistPrivacy();
  }

  function setHelpImproveModel(value: boolean) {
    helpImproveModel.value = value;
    persistPrivacy();
  }

  function setPublicChatSharing(value: boolean) {
    publicChatSharing.value = value;
    persistPrivacy();
  }

  function setShowChatHistory(value: boolean) {
    showChatHistory.value = value;
    persistPrivacy();
  }

  function resetPreferences() {
    enterToSend.value = DEFAULT_CHAT_PREFERENCES.enterToSend;
    autoScrollMessages.value = DEFAULT_CHAT_PREFERENCES.autoScrollMessages;
    defaultSidebarRail.value = DEFAULT_UI_PREFERENCES.defaultSidebarRail;
    fontSize.value = DEFAULT_UI_PREFERENCES.fontSize;
    fontStyle.value = DEFAULT_UI_PREFERENCES.fontStyle;
    locationMetadata.value = DEFAULT_PRIVACY_PREFERENCES.locationMetadata;
    helpImproveModel.value = DEFAULT_PRIVACY_PREFERENCES.helpImproveModel;
    publicChatSharing.value = DEFAULT_PRIVACY_PREFERENCES.publicChatSharing;
    showChatHistory.value = DEFAULT_PRIVACY_PREFERENCES.showChatHistory;

    persistChat();
    persistUi();
    persistPrivacy();
  }

  return {
    enterToSend,
    autoScrollMessages,
    defaultSidebarRail,
    fontSize,
    fontStyle,
    locationMetadata,
    helpImproveModel,
    publicChatSharing,
    showChatHistory,
    init,
    setEnterToSend,
    setAutoScrollMessages,
    setDefaultSidebarRail,
    setFontSize,
    setFontStyle,
    setLocationMetadata,
    setHelpImproveModel,
    setPublicChatSharing,
    setShowChatHistory,
    resetPreferences,
  };
});
