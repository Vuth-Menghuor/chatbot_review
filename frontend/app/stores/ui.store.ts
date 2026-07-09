import { defineStore } from 'pinia';
import { usePreferencesStore } from '~/stores/preferences.store';
import { readString, storageKeys, writeString } from '~/utils/storage';
import type { Message } from '~/types/message';
import type { SettingsSectionId } from '~/types/settings-nav';
import { isSettingsSectionId } from '~/types/settings-nav';
import { DEFAULT_APP_THEME, isAppThemeName, type AppThemeName } from '~/utils/theme/vuetifyThemes';

export type SidebarMode = 'desktop' | 'mobile';

export const useUiStore = defineStore('ui', {
  state: () => ({
    // Sidebar logic
    sidebarOpened: true,
    railMode: false,
    sidebarWidth: 300,
    isDragging: false,

    // App state
    filesPanelOpened: false,
    currentChatTitle: '',
    theme: DEFAULT_APP_THEME as AppThemeName,

    // Sources & Activity panel state
    activePanelType: 'files' as 'files' | 'sources',
    activeMessageForSources: null as Message | null,

    // Responsive state
    windowWidth: typeof window !== 'undefined' ? window.innerWidth : 1200,

    // Settings dialog (opened from sidebar user menu, etc.)
    settingsDialogOpen: false,
    settingsDialogSection: 'general' as SettingsSectionId,

    // Global search dialog (sidebar + ⌘K / Ctrl+K)
    searchDialogOpen: false,
  }),

  getters: {
    isMobile: (state) => state.windowWidth < 768,
    isTablet: (state) => state.windowWidth >= 768 && state.windowWidth < 1024,
    isDesktop: (state) => state.windowWidth >= 1024,

    // Sidebar responsive width
    computedSidebarWidth: (state) => {
      if (state.windowWidth < 768) return state.sidebarOpened ? 280 : 0;
      if (!state.sidebarOpened) return 0;
      return state.railMode ? 72 : state.sidebarWidth;
    },

    isSidebarMobile: () => (mode: SidebarMode) => mode === 'mobile',
    isSidebarDesktop: () => (mode: SidebarMode) => mode === 'desktop',

    isSidebarRail: (state) => (mode: SidebarMode) => mode === 'desktop' && state.railMode,

    showSidebarBrand: (state) => (mode: SidebarMode) => mode === 'mobile' || !state.railMode,

    showSidebarExpandedActions: (state) => (mode: SidebarMode) =>
      mode === 'mobile' || !state.railMode,

    showSidebarResizeHandle:
      (state) =>
      (mode: SidebarMode): boolean =>
        mode === 'desktop' && state.sidebarOpened && !state.railMode,

    sidebarClass:
      (state) =>
      (mode: SidebarMode): string[] => [
        mode === 'mobile'
          ? 'flex w-[280px]'
          : 'hidden md:flex relative shrink-0 border-r border-gray-200/50 dark:border-zinc-800',
        mode === 'desktop' && state.sidebarOpened ? 'translate-x-0' : '',
        mode === 'desktop' && !state.sidebarOpened
          ? '-translate-x-full w-0 invisible overflow-hidden border-none'
          : 'visible',
      ],

    sidebarStyle:
      (state) =>
      (mode: SidebarMode): Record<string, string> => {
        if (mode !== 'desktop') return {};

        const width = !state.sidebarOpened ? 0 : state.railMode ? 72 : state.sidebarWidth;
        return { width: `${width}px` };
      },

    sidebarRailToggleWrapperClass:
      (state) =>
      (mode: SidebarMode): string =>
        mode === 'desktop' && state.railMode ? 'w-full flex justify-start ml-1' : '',

    /** Collapsed sidebar icon buttons (projects, recents, etc.) — no box border */
    sidebarRailButtonClass: () =>
      'h-10 w-10 min-w-0 !border-0 !shadow-none text-gray-800 hover:bg-gray-200/50 dark:hover:bg-zinc-800 transition-colors',
  },

  actions: {
    /**
     * Centralized initialization to handle screen resize and initial state
     */
    init() {
      if (typeof window === 'undefined') return;

      this.handleResize();
      window.addEventListener('resize', this.handleResize);

      // Restore user preferences
      const savedWidth = readString(storageKeys.sidebarWidth);
      if (savedWidth) {
        const w = parseInt(savedWidth, 10);
        if (!Number.isNaN(w)) this.sidebarWidth = w;
      }

      const savedRail = readString(storageKeys.railMode);
      if (savedRail !== null) {
        this.railMode = savedRail === 'true';
      } else {
        const preferencesStore = usePreferencesStore();
        if (preferencesStore.defaultSidebarRail) {
          this.railMode = true;
        }
      }

      const savedTheme = readString(storageKeys.appTheme);
      if (isAppThemeName(savedTheme)) this.theme = savedTheme;
    },

    handleResize() {
      const prevIsMobile = this.isMobile;
      this.windowWidth = window.innerWidth;

      // Logic for high-performance UI transitions
      if (!prevIsMobile && this.isMobile) {
        // Entering Mobile: Auto-close sidebar for better UX
        this.sidebarOpened = false;
        this.filesPanelOpened = false;
      } else if (prevIsMobile && !this.isMobile) {
        // Entering Desktop: Restore sidebar if it's supposed to be open
        this.sidebarOpened = true;
      }
    },

    toggleFilesPanel() {
      this.filesPanelOpened = !this.filesPanelOpened;
    },

    openFilesPanel() {
      this.activePanelType = 'files';
      this.filesPanelOpened = true;
    },

    openSourcesPanel(message: Message) {
      this.activePanelType = 'sources';
      this.activeMessageForSources = message;
      this.filesPanelOpened = true;
    },

    openSidebar() {
      this.sidebarOpened = true;
    },

    closeSidebar() {
      this.sidebarOpened = false;
    },

    closeMobileSidebar() {
      if (this.isMobile) this.closeSidebar();
    },

    toggleSidebar() {
      if (this.isMobile) {
        this.sidebarOpened = !this.sidebarOpened;
      } else {
        // Desktop: Toggling usually means rail mode or full close
        if (this.railMode && this.sidebarOpened) {
          this.railMode = false;
        } else {
          this.sidebarOpened = !this.sidebarOpened;
        }
      }
    },

    toggleRail() {
      this.railMode = !this.railMode;
      writeString(storageKeys.railMode, String(this.railMode));
    },

    setSidebarWidth(width: number) {
      if (width < 240) {
        this.railMode = true;
      } else {
        this.railMode = false;
        this.sidebarWidth = Math.max(240, Math.min(450, width));
        writeString(storageKeys.sidebarWidth, String(this.sidebarWidth));
      }
      writeString(storageKeys.railMode, String(this.railMode));
    },

    setTheme(theme: AppThemeName) {
      this.theme = theme;
      writeString(storageKeys.appTheme, theme);
    },

    openSearchDialog() {
      this.closeMobileSidebar();
      this.searchDialogOpen = true;
    },

    closeSearchDialog() {
      this.searchDialogOpen = false;
    },

    openSettingsDialog(section: SettingsSectionId = 'general') {
      this.closeMobileSidebar();
      this.settingsDialogSection = isSettingsSectionId(section) ? section : 'general';
      this.settingsDialogOpen = true;
    },

    closeSettingsDialog() {
      this.settingsDialogOpen = false;
    },
  },
});
