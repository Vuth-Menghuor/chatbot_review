import type { Component } from 'vue';

/** Vuetify overlay `location` values used by tooltips and menus. */
export type TooltipLocation =
  | 'top'
  | 'bottom'
  | 'start'
  | 'end'
  | 'left'
  | 'right'
  | 'top start'
  | 'top end'
  | 'bottom start'
  | 'bottom end';

export interface FileTypeIconPreset {
  boxClass: string;
  icon: string;
}

export interface FilePreviewEmit {
  (e: 'remove', index: number): void;
}

export type NavbarShareType = 'private' | 'public';

export interface NavbarChatShareOption {
  id: NavbarShareType;
  title: string;
  description: string;
  icon: string;
}

export interface UseNavbarChatMoreMenuOptions {
  onShare?: () => void;
}

export type MenuItemTone = 'menu' | 'nav';

export type MenuDivider = {
  type: 'divider';
};

export type MenuHeader = {
  type: 'header';
  label: string;
};

/** Config shape for dropdown/menu rows (not the Vue component). */
export interface MenuRowConfig {
  id?: string;
  /** Resolved label (static). */
  label?: string;
  /** vue-i18n key; preferred over label when set. */
  labelKey?: string;
  value?: string;
  /** Vuetify icon name (e.g. `lucide-user`) or a Vue component. */
  icon?: Component | string;
  description?: string;
  suffix?: Component;
  shortcut?: string;
  danger?: boolean;
  disabled?: boolean;
  active?: boolean;
  /** Boxed icon on the left (search-style). */
  boxed?: boolean;
  /** Right-aligned meta text (e.g. search result date). */
  meta?: string;
  /** Context menu entries (⋯) shown on the right. */
  menuItems?: MenuEntry[];
  pinned?: boolean;
  /** Extra classes on the leading icon wrapper (project source file box). */
  leadingClass?: string;
  /** Rich panel row (project chat / sources). */
  appearance?: 'default' | 'select' | 'card';
  menuLocation?: TooltipLocation;
  class?: string;
  onClick?: () => void;
}

export interface MenuItem extends MenuRowConfig {
  type?: 'item';
}

export interface SubmenuItem extends MenuRowConfig {
  type: 'submenu';
  children?: MenuEntry[];
  custom?: boolean;
}

export type MenuEntry = MenuItem | SubmenuItem | MenuDivider | MenuHeader;
