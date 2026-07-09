import { storeToRefs } from 'pinia';
import { useUiStore } from '~/stores/ui.store';
import type { SettingsSectionId } from '~/types/settings-nav';

export function useSettingsDialog() {
  const uiStore = useUiStore();
  const { settingsDialogOpen, settingsDialogSection } = storeToRefs(uiStore);

  function openSettings(section: SettingsSectionId = 'general') {
    uiStore.openSettingsDialog(section);
  }

  function closeSettings() {
    uiStore.closeSettingsDialog();
  }

  return {
    settingsOpen: settingsDialogOpen,
    settingsSection: settingsDialogSection,
    openSettings,
    closeSettings,
  };
}
