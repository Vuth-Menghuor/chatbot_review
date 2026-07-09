import { computed } from 'vue';
import { storeToRefs } from 'pinia';
import { usePreferencesStore } from '~/stores/preferences.store';
import { formatModKey, formatShortcut } from '~/utils/keyboard/formatShortcut';

export type KeyboardShortcutCategory = 'composer' | 'navigation' | 'settings' | 'general';

export interface KeyboardShortcutRow {
  id: string;
  label: string;
  keys: string;
}

export interface KeyboardShortcutGroup {
  id: KeyboardShortcutCategory;
  titleKey: string;
  items: KeyboardShortcutRow[];
}

export function useKeyboardShortcutCatalog() {
  const { t } = useI18n();
  const preferencesStore = usePreferencesStore();
  const { enterToSend } = storeToRefs(preferencesStore);

  const mod = computed(() => formatModKey());

  const groups = computed<KeyboardShortcutGroup[]>(() => {
    const sendKeys = enterToSend.value ? 'Enter' : formatShortcut([mod.value, 'Enter']);
    const newLineKeys = enterToSend.value ? 'Shift Enter' : 'Enter';

    return [
      {
        id: 'composer',
        titleKey: 'settings.keyboard.groups.composer',
        items: [
          {
            id: 'sendMessage',
            label: t('settings.keyboard.shortcuts.sendMessage.label'),
            keys: sendKeys,
          },
          {
            id: 'newLine',
            label: t('settings.keyboard.shortcuts.newLine.label'),
            keys: newLineKeys,
          },
          {
            id: 'autoScroll',
            label: t('settings.chat.autoScroll.title'),
            keys: '',
          },
        ],
      },
      {
        id: 'navigation',
        titleKey: 'settings.keyboard.groups.navigation',
        items: [
          {
            id: 'search',
            label: t('settings.keyboard.shortcuts.search.label'),
            keys: formatShortcut([mod.value, 'K']),
          },
          {
            id: 'newChat',
            label: t('settings.keyboard.shortcuts.newChat.label'),
            keys: formatShortcut([mod.value, 'Shift', 'N']),
          },
          {
            id: 'toggleSidebar',
            label: t('settings.keyboard.shortcuts.toggleSidebar.label'),
            keys: formatShortcut([mod.value, 'B']),
          },
        ],
      },
      {
        id: 'settings',
        titleKey: 'settings.keyboard.groups.settings',
        items: [
          {
            id: 'openSettings',
            label: t('settings.keyboard.shortcuts.openSettings.label'),
            keys: formatShortcut([mod.value, ',']),
          },
          {
            id: 'openKeyboard',
            label: t('settings.keyboard.shortcuts.openKeyboard.label'),
            keys: formatShortcut([mod.value, '/']),
          },
        ],
      },
      {
        id: 'general',
        titleKey: 'settings.keyboard.groups.general',
        items: [
          {
            id: 'closeDialog',
            label: t('settings.keyboard.shortcuts.closeDialog.label'),
            keys: 'Esc',
          },
        ],
      },
    ];
  });

  return { groups };
}
