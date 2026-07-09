import { computed, useSlots, type Component, type ComputedRef, type Ref } from 'vue';
import type { MenuEntry, MenuItemTone } from '~/types/ui-menu';

export type MenuItemAppearance = 'default' | 'select' | 'card';

const navItemShell =
  'group text-base text-high-emphasis transition-all duration-300 cursor-pointer hover:!bg-gray-100 hover:text-gray-700 dark:hover:!bg-zinc-800 dark:hover:text-zinc-300 [&_.v-list-item__overlay]:!opacity-0';

const menuItemShell =
  'group mx-1 min-h-10 rounded-xl py-1.5 px-3 transition-colors cursor-pointer hover:!bg-gray-100 hover:text-gray-700 dark:hover:!bg-zinc-800 dark:hover:text-zinc-300 [&_.v-list-item__overlay]:!opacity-0';

const navItemRail = `${navItemShell} mx-auto min-h-9 w-10 justify-center px-0`;
const navItemExpanded = `${navItemShell} min-h-9 pl-3 pr-3`;
const navItemActive = '!bg-gray-200 !font-bold dark:!bg-zinc-700';

const projectItem =
  'group !mx-0 w-full !min-h-0 !py-2.5 !px-3 rounded-xl border-b border-gray-100 last:border-b-0 dark:border-zinc-900 [&_.v-list-item__prepend]:mr-4 [&_.v-list-item__overlay]:!opacity-0';

const menuItemActive = '!bg-gray-200 dark:!bg-zinc-700';
const menuItemDanger =
  'text-error [&_.lucide]:!text-error [&_span]:!text-error hover:!bg-error/10 hover:!text-error hover:[&_.lucide]:!text-error hover:[&_span]:!text-error';
const menuItemDisabled = 'pointer-events-none opacity-50';

const selectItemShell =
  'group cursor-pointer bg-gray-50 text-gray-700 dark:bg-zinc-800/50 dark:text-zinc-300 [&_.v-list-item__overlay]:!opacity-0 hover:!bg-gray-50 hover:!text-inherit dark:hover:!bg-zinc-800/50';

const selectDividerRow =
  '!mx-0 !min-h-0 !rounded-none !py-3.5 !px-4 border-b border-gray-200 last:border-b-0 dark:border-zinc-700';
const selectRowActive =
  '!bg-gray-200 !text-gray-900 dark:!bg-zinc-700 dark:!text-zinc-100 [&_.truncate]:font-semibold [&_.text-medium-emphasis]:!text-gray-500 dark:[&_.text-medium-emphasis]:!text-zinc-400 [&_.lucide]:!text-gray-700 dark:[&_.lucide]:!text-zinc-200 hover:!bg-gray-200 dark:hover:!bg-zinc-700';

const listTitle =
  'truncate text-base font-medium leading-tight text-high-emphasis dark:text-zinc-100';
const projectTitle =
  'block overflow-hidden text-ellipsis whitespace-normal text-[0.9375rem] font-bold leading-snug text-gray-900 dark:text-zinc-200';
const projectSubtitle = 'mt-1 block truncate text-sm leading-relaxed text-gray-500 dark:text-zinc-500';
const navSubtitle = 'text-xs text-medium-emphasis dark:text-zinc-400';

const iconDecorative = 'pointer-events-none';
const iconDecorativeNav = 'mr-3 pointer-events-none';

export interface UseMenuItemOptions {
  tone: Ref<MenuItemTone> | MenuItemTone;
  appearance: Ref<MenuItemAppearance> | MenuItemAppearance;
  labelKey: Ref<string | undefined> | string | undefined;
  label: Ref<string | undefined> | string | undefined;
  description: Ref<string | undefined> | string | undefined;
  subtitle: Ref<string | undefined> | string | undefined;
  tooltip: Ref<string | undefined> | string | undefined;
  icon: Ref<Component | string | undefined> | Component | string | undefined;
  shortcut: Ref<string | undefined> | string | undefined;
  meta: Ref<string | undefined> | string | undefined;
  suffix: Ref<Component | undefined> | Component | undefined;
  danger: Ref<boolean> | boolean;
  disabled: Ref<boolean> | boolean;
  active: Ref<boolean> | boolean;
  boxed: Ref<boolean> | boolean;
  rail: Ref<boolean> | boolean;
  menuItems: Ref<MenuEntry[] | undefined> | MenuEntry[] | undefined;
  leadingClass: Ref<string | undefined> | string | undefined;
}

function unwrap<T>(value: Ref<T> | T): T {
  return typeof value === 'object' && value !== null && 'value' in value
    ? (value as Ref<T>).value
    : value;
}

export function useMenuItem(options: UseMenuItemOptions) {
  const slots = useSlots();

  const displayLabel = computed(() => {
    const labelKey = unwrap(options.labelKey);
    return labelKey ? undefined : unwrap(options.label);
  });

  const tooltipText = computed(() => {
    const tooltip = unwrap(options.tooltip);
    const label = unwrap(options.label);
    return tooltip ?? label ?? '';
  });

  const secondaryText = computed(
    () => unwrap(options.description) || unwrap(options.subtitle),
  );

  const showContextMenu = computed(() => {
    const rail = unwrap(options.rail);
    const menuItems = unwrap(options.menuItems);
    return !rail && !!menuItems?.length && !slots.actions;
  });

  const hasAppend = computed(
    () =>
      !!slots.append ||
      !!unwrap(options.meta) ||
      !!unwrap(options.shortcut) ||
      !!unwrap(options.suffix) ||
      showContextMenu.value,
  );

  const listItemClass = computed(() => {
    const tone = unwrap(options.tone);
    const rail = unwrap(options.rail);
    const active = unwrap(options.active);
    const appearance = unwrap(options.appearance);
    const boxed = unwrap(options.boxed);
    const danger = unwrap(options.danger);
    const disabled = unwrap(options.disabled);

    if (tone === 'nav') {
      const isCard = appearance === 'card';
      return [
        isCard ? projectItem : rail ? navItemRail : navItemExpanded,
        active ? navItemActive : '',
        disabled ? menuItemDisabled : 'cursor-pointer',
      ];
    }
    if (appearance === 'select') {
      return [
        selectItemShell,
        selectDividerRow,
        active ? selectRowActive : '',
        disabled ? menuItemDisabled : '',
      ];
    }

    return [
      menuItemShell,
      active && !boxed ? menuItemActive : '',
      danger ? menuItemDanger : '',
      disabled ? menuItemDisabled : '',
    ];
  });

  const titleClass = computed(() => {
    if (unwrap(options.danger)) return `${listTitle} text-error`;
    if (unwrap(options.tone) === 'nav' && unwrap(options.appearance) === 'card') {
      return projectTitle;
    }
    return listTitle;
  });

  const subtitleClass = computed(() =>
    unwrap(options.tone) === 'nav' && unwrap(options.appearance) === 'card'
      ? projectSubtitle
      : navSubtitle,
  );

  const showNavPrepend = computed(() => {
    const tone = unwrap(options.tone);
    const rail = unwrap(options.rail);
    const icon = unwrap(options.icon);
    return tone === 'nav' && (icon || slots.leading) && !rail;
  });

  const showNavRailIcon = computed(() => {
    const tone = unwrap(options.tone);
    const rail = unwrap(options.rail);
    const icon = unwrap(options.icon);
    return tone === 'nav' && rail && !!icon;
  });

  const iconSize = computed(() => {
    const boxed = unwrap(options.boxed);
    const tone = unwrap(options.tone);
    return boxed && tone === 'menu' ? 'x-small' : 'small';
  });

  const iconDecorativeClass = computed(() => {
    const tone = unwrap(options.tone);
    const rail = unwrap(options.rail);
    return tone === 'nav' && !rail ? iconDecorativeNav : iconDecorative;
  });

  return {
    displayLabel,
    tooltipText,
    secondaryText,
    showContextMenu,
    hasAppend,
    listItemClass,
    titleClass,
    subtitleClass,
    showNavPrepend,
    showNavRailIcon,
    iconSize,
    iconDecorativeClass,
  };
}

/** Convenience wrapper for `defineProps` + `useMenuItem`. */
export function useMenuItemFromProps(getters: {
  tone: () => MenuItemTone;
  appearance: () => MenuItemAppearance;
  labelKey: () => string | undefined;
  label: () => string | undefined;
  description: () => string | undefined;
  subtitle: () => string | undefined;
  tooltip: () => string | undefined;
  icon: () => Component | string | undefined;
  shortcut: () => string | undefined;
  meta: () => string | undefined;
  suffix: () => Component | undefined;
  danger: () => boolean;
  disabled: () => boolean;
  active: () => boolean;
  boxed: () => boolean;
  rail: () => boolean;
  menuItems: () => MenuEntry[] | undefined;
  leadingClass: () => string | undefined;
}) {
  return useMenuItem({
    tone: computed(getters.tone),
    appearance: computed(getters.appearance),
    labelKey: computed(getters.labelKey),
    label: computed(getters.label),
    description: computed(getters.description),
    subtitle: computed(getters.subtitle),
    tooltip: computed(getters.tooltip),
    icon: computed(getters.icon),
    shortcut: computed(getters.shortcut),
    meta: computed(getters.meta),
    suffix: computed(getters.suffix),
    danger: computed(getters.danger),
    disabled: computed(getters.disabled),
    active: computed(getters.active),
    boxed: computed(getters.boxed),
    rail: computed(getters.rail),
    menuItems: computed(getters.menuItems),
    leadingClass: computed(getters.leadingClass),
  });
}
