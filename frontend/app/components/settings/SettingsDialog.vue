<template>
  <v-dialog
    v-model="isOpen"
    :max-width="isMobile ? undefined : width"
    :fullscreen="isMobile"
    transition="dialog-bottom-transition"
    class="settings-dialog overflow-hidden"
    :content-class="isMobile ? 'settings-dialog-content--mobile' : ''"
  >
    <div
      class="flex h-dvh min-h-0 flex-col-reverse overflow-hidden bg-white text-base font-sans dark:bg-zinc-950 md:h-[min(720px,85dvh)] md:flex-row md:rounded-2xl md:border md:border-gray-200 md:shadow-xl dark:md:border-zinc-800"
    >
      <!-- Bottom nav on mobile, left sidebar on desktop -->
      <aside
        class="settings-mobile-nav shrink-0 border-t border-gray-200 bg-white/95 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-900/95 md:flex md:w-[220px] md:flex-col md:border-t-0 md:border-r md:bg-white dark:md:bg-zinc-900"
      >
        <nav
          class="flex w-full items-stretch gap-0 px-1 py-1.5 md:flex-1 md:flex-col md:gap-0 md:space-y-0.5 md:overflow-y-auto md:px-2 md:pb-4 md:pt-3"
          role="tablist"
        >
          <button
            v-for="item in navItems"
            :key="item.id"
            type="button"
            role="tab"
            :aria-selected="activeSection === item.id"
            :aria-label="item.label"
            class="settings-mobile-nav-item flex min-h-14 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-lg px-0.5 py-1.5 text-center text-[0.625rem] font-medium leading-tight transition-colors md:min-h-0 md:w-full md:flex-none md:flex-row md:gap-3 md:px-3 md:py-2.5 md:text-left md:text-base"
            :class="
              activeSection === item.id
                ? 'bg-gray-100 font-semibold text-gray-950 dark:bg-zinc-800 dark:text-white'
                : 'text-high-emphasis hover:bg-gray-100 dark:text-zinc-300 dark:hover:bg-zinc-800/60 dark:hover:text-white'
            "
            @click="selectSection(item.id)"
          >
            <component
              :is="item.icon"
              class="h-5 w-5 shrink-0 text-current opacity-80 md:h-4 md:w-4"
              aria-hidden="true"
            />
            <span class="w-full px-0.5 text-center leading-tight break-words md:max-w-none md:truncate md:text-left">
              {{ item.label }}
            </span>
          </button>
        </nav>
      </aside>

      <!-- Main column: sticky header + scrollable content -->
      <div class="flex min-h-0 min-w-0 flex-1 flex-col bg-white dark:bg-zinc-950">
        <header
          class="sticky top-0 z-10 flex shrink-0 items-start justify-between gap-2 border-b border-gray-200 bg-white/95 px-4 py-3 backdrop-blur-sm sm:gap-3 sm:px-5 sm:py-4 md:px-6 dark:border-zinc-800 dark:bg-zinc-950/95"
        >
          <Transition name="settings-header" mode="out-in">
            <div :key="headerKey" class="min-w-0 flex-1">
              <h2 class="settings-section-title">{{ headerTitle }}</h2>
              <p v-if="headerDescription" class="settings-section-desc">
                {{ headerDescription }}
              </p>
            </div>
          </Transition>

          <div class="flex shrink-0 items-center gap-1">
            <BaseButton
              variant="text"
              size="small"
              :prepend-icon="RotateCcwIcon"
              :aria-label="$t('settings.reset.aria')"
              :tooltip="$t('settings.reset.aria')"
              custom-class="min-w-0 text-gray-600 hover:bg-gray-200/80 dark:text-zinc-400 dark:hover:bg-zinc-800"
              @click="resetSettings"
            >
              <span class="hidden sm:inline">
                {{ resetStatusText }}
              </span>
            </BaseButton>

            <BaseIconButton
              :icon="XIcon"
              :aria-label="$t('common.close')"
              custom-class="shrink-0 text-gray-600 hover:bg-gray-200/80 dark:text-zinc-400 dark:hover:bg-zinc-800"
              @click="close"
            />
          </div>
        </header>

        <div ref="scrollMainRef" class="custom-scrollbar min-h-0 flex-1 overflow-y-auto">
          <div
            :key="activeSection"
            class="settings-content p-4 text-base text-high-emphasis sm:p-5 md:p-6 dark:text-zinc-100"
          >
            <General
              v-if="activeSection === 'general'"
              v-model:active-language="activeLanguage"
              :languages="languages"
            />
            <AccountSection v-else-if="activeSection === 'account'" />
            <NotificationsSection v-else-if="activeSection === 'notifications'" />
            <KeyboardSection v-else-if="activeSection === 'keyboard'" />
            <PrivacySection v-else-if="activeSection === 'privacy'" />
          </div>
        </div>
      </div>
    </div>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { storeToRefs } from 'pinia';
import {
  BellIcon,
  CircleUserIcon,
  KeyboardIcon,
  RotateCcwIcon,
  SettingsIcon,
  ShieldIcon,
  XIcon,
} from 'lucide-vue-next';
import { useLanguages } from '~/composables/useLanguages';
import { useSettingsScrollSpy } from '~/composables/settings/useSettingsScrollSpy';
import { useSettingsSpyMeta } from '~/composables/settings/useSettingsSpyMeta';
import { useNotificationStore } from '~/stores/notification.store';
import { usePreferencesStore } from '~/stores/preferences.store';
import { useUiStore } from '~/stores/ui.store';
import type { SettingsNavItem, SettingsNavSectionId } from '~/types/settings-nav';
import { DEFAULT_APP_THEME } from '~/utils/theme/vuetifyThemes';
import AccountSection from './AccountSection.vue';
import General from './General/index.vue';
import NotificationsSection from './NotificationsSection.vue';
import KeyboardSection from './KeyboardSection.vue';
import PrivacySection from './PrivacySection.vue';

withDefaults(
  defineProps<{
    width?: string | number;
  }>(),
  {
    width: 960,
  },
);

const sectionMeta: Record<
  SettingsNavSectionId,
  { titleKey: string; descriptionKey?: string }
> = {
  account: {
    titleKey: 'settings.account.title',
    descriptionKey: 'settings.account.description',
  },
  general: { titleKey: 'settings.nav.general', descriptionKey: 'settings.general.description' },
  notifications: {
    titleKey: 'settings.notifications.title',
    descriptionKey: 'settings.notifications.description',
  },
  keyboard: {
    titleKey: 'settings.keyboard.title',
    descriptionKey: 'settings.keyboard.description',
  },
  privacy: {
    titleKey: 'settings.privacy.title',
    descriptionKey: 'settings.privacy.description',
  },
};

const uiStore = useUiStore();
const preferencesStore = usePreferencesStore();
const notificationStore = useNotificationStore();
const { settingsDialogOpen, settingsDialogSection } = storeToRefs(uiStore);
const isMobile = computed(() => uiStore.isMobile);

const scrollMainRef = ref<HTMLElement | null>(null);
const resetDone = ref(false);
let resetStatusTimer: ReturnType<typeof window.setTimeout> | undefined;
const { activeSpyId, refreshSpy, resetSpy } = useSettingsScrollSpy(scrollMainRef);
const { spyHeaders } = useSettingsSpyMeta();

const isOpen = computed({
  get: () => settingsDialogOpen.value,
  set: (open) => {
    if (open) {
      settingsDialogOpen.value = true;
      return;
    }
    uiStore.closeSettingsDialog();
  },
});

const activeSection = computed({
  get: () => settingsDialogSection.value,
  set: (section) => {
    settingsDialogSection.value = section;
  },
});

const { t } = useI18n();
const { languages, activeLanguage } = useLanguages();
const { setTheme } = useAppTheme();

const fallbackHeader = computed(() => {
  const meta = sectionMeta[activeSection.value];
  return {
    title: t(meta.titleKey),
    description: meta.descriptionKey ? t(meta.descriptionKey) : '',
  };
});

const headerTitle = computed(() => {
  const spy = activeSpyId.value ? spyHeaders.value[activeSpyId.value] : null;
  return spy?.title ?? fallbackHeader.value.title;
});

const headerDescription = computed(() => {
  const spy = activeSpyId.value ? spyHeaders.value[activeSpyId.value] : null;
  return spy?.description ?? fallbackHeader.value.description;
});

const headerKey = computed(() => `${activeSection.value}:${activeSpyId.value ?? 'default'}`);

const navItems = computed<SettingsNavItem[]>(() => [
  { id: 'account', label: t('settings.nav.account'), icon: CircleUserIcon },
  { id: 'general', label: t('settings.nav.general'), icon: SettingsIcon },
  { id: 'notifications', label: t('settings.nav.notifications'), icon: BellIcon },
  { id: 'keyboard', label: t('settings.nav.keyboard'), icon: KeyboardIcon },
  { id: 'privacy', label: t('settings.nav.privacy'), icon: ShieldIcon },
]);

const resetStatusText = computed(() =>
  resetDone.value ? t('settings.reset.success') : t('settings.reset.button'),
);

watch(activeSection, async () => {
  resetSpy();
  if (scrollMainRef.value) {
    scrollMainRef.value.scrollTop = 0;
  }
  await nextTick();
  refreshSpy();
});

watch(isOpen, async (open) => {
  if (!open) return;
  await nextTick();
  refreshSpy();
});

onBeforeUnmount(() => {
  if (resetStatusTimer) {
    window.clearTimeout(resetStatusTimer);
  }
});

function close() {
  uiStore.closeSettingsDialog();
}

function selectSection(id: SettingsNavSectionId) {
  settingsDialogSection.value = id;
}

function resetSettings() {
  preferencesStore.resetPreferences();
  notificationStore.resetNotificationPreferences();
  setTheme(DEFAULT_APP_THEME);
  activeLanguage.value = 'en';

  resetDone.value = true;
  if (resetStatusTimer) {
    window.clearTimeout(resetStatusTimer);
  }
  resetStatusTimer = window.setTimeout(() => {
    resetDone.value = false;
    resetStatusTimer = undefined;
  }, 1600);
}
</script>

<style scoped>
.settings-header-enter-active,
.settings-header-leave-active {
  transition:
    opacity 0.15s ease,
    transform 0.15s ease;
}

.settings-header-enter-from,
.settings-header-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
</style>
