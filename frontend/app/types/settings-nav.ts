import type { Component } from 'vue';

export const SETTINGS_SECTION_IDS = [
  'account',
  'general',
  'notifications',
  'keyboard',
  'privacy',
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTION_IDS)[number];

/** Sections shown in the settings dialog left nav. */
export const SETTINGS_NAV_SECTION_IDS = [
  'account',
  'general',
  'notifications',
  'keyboard',
  'privacy',
] as const;

export type SettingsNavSectionId = (typeof SETTINGS_NAV_SECTION_IDS)[number];

export interface SettingsNavItem {
  id: SettingsNavSectionId;
  label: string;
  icon: Component;
}

export function isSettingsSectionId(value: string): value is SettingsSectionId {
  return SETTINGS_SECTION_IDS.includes(value as SettingsSectionId);
}
