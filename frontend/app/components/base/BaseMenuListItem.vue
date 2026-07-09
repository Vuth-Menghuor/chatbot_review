<script setup lang="ts">
import { computed, type Component } from 'vue';
import type { MenuEntry, MenuItem, MenuItemTone, SubmenuItem, TooltipLocation } from '~/types/ui-menu';
import { useMenuItemFromProps, type MenuItemAppearance } from '~/composables/ui/useMenuItem';

export type BaseMenuListItemAppearance = MenuItemAppearance;

interface Props {
  tone?: MenuItemTone;
  appearance?: BaseMenuListItemAppearance;
  label?: string;
  labelKey?: string;
  description?: string;
  subtitle?: string;
  icon?: Component | string;
  suffix?: Component;
  shortcut?: string;
  meta?: string;
  danger?: boolean;
  disabled?: boolean;
  active?: boolean;
  boxed?: boolean;
  rail?: boolean;
  tooltip?: string;
  menuItems?: MenuEntry[];
  pinned?: boolean;
  leadingClass?: string;
  /** Context menu overlay position (sidebar nav defaults to the right). */
  menuLocation?: TooltipLocation;
  rounded?: string | boolean;
}

const props = withDefaults(defineProps<Props>(), {
  tone: 'menu',
  appearance: 'default',
  boxed: false,
  rail: false,
  pinned: false,
  rounded: 'lg',
});

const emit = defineEmits<{
  click: [event: MouseEvent | KeyboardEvent];
  'menu-select': [item: MenuItem | SubmenuItem];
}>();

defineOptions({ inheritAttrs: false });

const {
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
} = useMenuItemFromProps({
  tone: () => props.tone,
  appearance: () => props.appearance,
  labelKey: () => props.labelKey,
  label: () => props.label,
  description: () => props.description,
  subtitle: () => props.subtitle,
  tooltip: () => props.tooltip,
  icon: () => props.icon,
  shortcut: () => props.shortcut,
  meta: () => props.meta,
  suffix: () => props.suffix,
  danger: () => props.danger,
  disabled: () => props.disabled,
  active: () => props.active,
  boxed: () => props.boxed,
  rail: () => props.rail,
  menuItems: () => props.menuItems,
  leadingClass: () => props.leadingClass,
});

const navIconClass =
  'text-high-emphasis group-hover:text-gray-700 dark:group-hover:text-zinc-300';

const menuIconClass = computed(() =>
  props.danger
    ? 'pointer-events-none text-error'
    : 'pointer-events-none shrink-0 text-high-emphasis',
);

const contextMenuLocation = computed<TooltipLocation>(() => {
  if (props.menuLocation) return props.menuLocation;
  if (props.tone === 'nav') return 'end';
  if (props.appearance === 'card') return 'end';
  return 'bottom start';
});

function onClick(event: MouseEvent | KeyboardEvent) {
  if (props.disabled) return;
  emit('click', event);
}

function onMenuSelect(item: MenuItem | SubmenuItem) {
  emit('menu-select', item);
}
</script>

<template>
  <v-list-item
    v-bind="$attrs"
    slim
    :rounded="rounded"
    density="compact"
    :active="active"
    :disabled="disabled"
    :class="listItemClass"
    @click="onClick"
  >
    <template v-if="showNavPrepend" #prepend>
      <slot name="leading">
        <div
          v-if="leadingClass"
          :class="[
            'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl shadow-sm transition-transform group-hover:rotate-3 [&_.lucide]:h-6 [&_.lucide]:w-6 [&_.lucide]:text-white',
            leadingClass,
          ]"
        >
          <BaseIconButton
            v-if="icon && typeof icon !== 'string'"
            decorative
            :icon="icon"
            size="small"
            custom-class="pointer-events-none text-white"
          />
        </div>
        <template v-else>
          <v-icon
            v-if="typeof icon === 'string'"
            :icon="icon"
            size="small"
            :class="iconDecorativeClass"
          />
          <BaseIconButton
            v-else-if="icon"
            decorative
            :icon="icon"
            size="small"
            :custom-class="iconDecorativeClass"
          />
        </template>
      </slot>
    </template>

    <template v-if="showNavRailIcon" #default>
      <BaseTooltip v-if="tooltipText" :text="tooltipText" location="right">
        <template #activator="{ props: tipProps }">
          <div v-bind="tipProps" class="flex justify-center">
            <slot name="leading">
              <v-icon
                v-if="typeof icon === 'string'"
                :icon="icon"
                size="small"
                :class="navIconClass"
              />
              <BaseIconButton
                v-else-if="icon && typeof icon !== 'string'"
                decorative
                :icon="icon"
                :size="iconSize"
                custom-class="pointer-events-none"
              />
            </slot>
          </div>
        </template>
      </BaseTooltip>
    </template>

    <template v-else-if="tone === 'nav' && !rail" #default>
      <slot name="default">
        <v-list-item-title>
          <span
            :class="
              appearance === 'card'
                ? 'block overflow-hidden text-ellipsis whitespace-normal text-[0.9375rem] font-bold leading-snug text-gray-900 dark:text-zinc-200'
                : 'block truncate text-base text-high-emphasis dark:text-zinc-100 group-hover:text-gray-700 dark:group-hover:text-zinc-300'
            "
          >
            <template v-if="labelKey">{{ $t(labelKey) }}</template>
            <template v-else>{{ displayLabel }}</template>
          </span>
        </v-list-item-title>
        <v-list-item-subtitle v-if="secondaryText" :class="subtitleClass">
          {{ secondaryText }}
        </v-list-item-subtitle>
      </slot>
    </template>

    <template v-else-if="tone === 'menu'" #default>
      <div class="flex w-full min-w-0 items-center gap-2.5">
        <div class="shrink-0">
        <slot name="leading">
          <div
            v-if="icon && boxed"
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-current/25 bg-surface"
          >
            <v-icon
              v-if="typeof icon === 'string'"
              :icon="icon"
              size="small"
              :class="navIconClass"
            />
            <BaseIconButton
              v-else-if="icon && typeof icon !== 'string'"
              decorative
              :icon="icon"
              :size="iconSize"
              :custom-class="menuIconClass"
            />
          </div>
          <template v-else-if="icon">
            <v-icon
              v-if="typeof icon === 'string'"
              :icon="icon"
              size="small"
              :class="menuIconClass"
            />
            <BaseIconButton
              v-else-if="typeof icon !== 'string'"
              decorative
              :icon="icon"
              size="small"
              :custom-class="menuIconClass"
            />
          </template>
        </slot>
        </div>

        <div v-if="!$slots.default" class="flex min-w-0 flex-1 flex-col">
          <span :class="titleClass">
            <template v-if="labelKey">{{ $t(labelKey) }}</template>
            <template v-else>{{ displayLabel }}</template>
          </span>
          <span v-if="secondaryText" class="truncate text-[0.6875rem] leading-4 text-medium-emphasis dark:text-zinc-400">
            {{ secondaryText }}
          </span>
        </div>
        <div v-else class="flex min-w-0 flex-1 flex-col">
          <slot />
        </div>

        <div v-if="hasAppend" class="ml-auto shrink-0 self-center">
          <div class="flex shrink-0 items-center gap-1">
            <slot name="actions">
              <BaseContextMenu
                v-if="showContextMenu"
                :items="menuItems!"
                :active="active"
                :pinned="pinned"
                :location="contextMenuLocation"
                @select="onMenuSelect"
              />
            </slot>
            <slot name="append">
              <span v-if="meta" class="shrink-0 whitespace-nowrap pl-1 text-xs leading-tight text-medium-emphasis">{{ meta }}</span>
              <component :is="suffix" v-else-if="suffix" class="lucide h-4 w-4 shrink-0 text-medium-emphasis" />
              <kbd
                v-else-if="shortcut"
                class="ml-1 shrink-0 rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 font-mono text-[0.625rem] text-white dark:border-zinc-300 dark:bg-zinc-100 dark:text-black"
              >
                {{ shortcut }}
              </kbd>
            </slot>
          </div>
        </div>
      </div>
    </template>

    <template v-if="tone === 'nav' && !rail && hasAppend" #append>
      <div
        :class="[
          'flex shrink-0 items-center gap-1',
          appearance === 'card' ? 'flex h-10 min-w-[60px] flex-col items-end justify-center pr-1' : '',
        ]"
      >
        <slot name="append">
          <span
            v-if="meta && appearance === 'card'"
            class="text-xs text-gray-400 transition-opacity group-hover:hidden dark:text-zinc-600"
          >
            {{ meta }}
          </span>
          <span v-else-if="meta" class="shrink-0 whitespace-nowrap pl-1 text-xs leading-tight text-medium-emphasis">{{ meta }}</span>
          <component :is="suffix" v-else-if="suffix" class="lucide h-4 w-4 shrink-0 text-medium-emphasis" />
          <kbd
            v-else-if="shortcut"
            class="ml-1 shrink-0 rounded border border-gray-700 bg-gray-800 px-1.5 py-0.5 font-mono text-[0.625rem] text-white dark:border-zinc-300 dark:bg-zinc-100 dark:text-black"
          >
            {{ shortcut }}
          </kbd>
        </slot>
        <div
          v-if="showContextMenu"
          :class="appearance === 'card' ? 'hidden min-w-10 items-center justify-end group-hover:flex' : ''"
        >
          <BaseContextMenu
            :items="menuItems!"
            :active="active"
            :pinned="pinned"
            :width="200"
            :location="contextMenuLocation"
            :offset="8"
            @select="onMenuSelect"
          />
        </div>
      </div>
    </template>
  </v-list-item>
</template>
