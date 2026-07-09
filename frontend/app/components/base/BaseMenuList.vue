<script setup lang="ts">
import { computed } from 'vue';
import { ChevronRightIcon } from 'lucide-vue-next';
import type { MenuEntry, MenuItem, MenuItemTone, SubmenuItem } from '~/types/ui-menu';

interface Props {
  items?: MenuEntry[];
  width?: string | number;
  fullWidth?: boolean;
  tone?: MenuItemTone;
  bgColor?: string;
  plain?: boolean;
  listClass?: string;
}

const props = withDefaults(defineProps<Props>(), {
  items: () => [],
  width: 210,
  fullWidth: false,
  tone: 'menu',
  plain: false,
  listClass: '',
});

const emit = defineEmits<{
  select: [item: MenuItem | SubmenuItem];
}>();

function isMenuItem(entry: MenuEntry): entry is MenuItem {
  return !entry.type || entry.type === 'item';
}

function entryKey(entry: MenuEntry, index: number): string | number {
  if (isMenuItem(entry) || entry.type === 'submenu') {
    return entry.id ?? entry.value ?? index;
  }
  return index;
}

function onItemClick(item: MenuItem) {
  item.onClick?.();
  emit('select', item);
}

const resolvedBgColor = computed(() => {
  if (props.bgColor !== undefined) return props.bgColor;
  if (props.tone === 'nav' || props.plain) return 'transparent';
  return 'surface';
});

const rootListClass = computed(() => {
  const panel = props.plain
    ? 'border-0 bg-transparent py-0 shadow-none'
    : props.tone === 'nav'
      ? 'flex flex-col gap-0.5 bg-transparent p-0'
      : 'overflow-hidden rounded-lg border border-current/25 bg-surface py-1 shadow-md';
  const full = props.fullWidth
    ? 'w-full max-w-full [&_.v-list-item]:mx-0 [&_.v-list-item]:w-full [&_.v-list-item]:px-4 [&_.v-list-item_.v-list-item__content]:min-w-0 [&_.v-list-item_.v-list-item__content]:w-full [&_.v-list-item_.v-list-item__content]:flex-1'
    : '';
  return [panel, full, props.listClass].filter(Boolean).join(' ');
});

const listWidth = computed(() => {
  if (props.tone === 'nav' || props.fullWidth) return undefined;
  return props.width;
});
</script>

<template>
  <v-list :bg-color="resolvedBgColor" :class="rootListClass" density="compact" :width="listWidth">
    <slot name="header" />
    <slot name="prepend" />

    <template v-for="(item, index) in items" :key="entryKey(item, index)">
      <v-divider v-if="item.type === 'divider'" class="my-1 border-current/25" />

      <div
        v-else-if="item.type === 'header'"
        class="sticky top-[-0.5rem] z-[1] bg-white/95 px-4 py-2 text-[0.8125rem] font-semibold uppercase tracking-wider text-gray-400 backdrop-blur-sm dark:bg-zinc-950/95 dark:text-zinc-500"
      >
        {{ item.label }}
      </div>

      <v-menu v-else-if="item.type === 'submenu'" submenu location="end top" open-on-hover open-on-click
        :offset="[0, 8]">
        <template #activator="{ props: subProps }">
          <BaseMenuListItem v-bind="subProps" :tone="tone" :label="item.label" :label-key="item.labelKey"
            :icon="item.icon" :boxed="item.boxed" :class="item.class">
            <template #append>
              <BaseIconButton decorative :icon="ChevronRightIcon" size="x-small"
                custom-class="pointer-events-none" />
            </template>
          </BaseMenuListItem>
        </template>

        <slot v-if="item.custom" :name="`submenu-${item.id || index}`" :item="item" />
        <BaseMenuList v-else-if="item.children" :items="item.children" :tone="tone" :width="240"
          @select="emit('select', $event)" />
      </v-menu>

      <BaseMenuListItem v-else-if="isMenuItem(item)" :tone="tone" :label="item.label" :label-key="item.labelKey"
        :description="item.description" :icon="item.icon" :suffix="item.suffix" :shortcut="item.shortcut"
        :meta="item.meta" :appearance="item.appearance" :menu-items="item.menuItems" :pinned="item.pinned"
        :leading-class="item.leadingClass" :menu-location="item.menuLocation" :danger="item.danger"
        :disabled="item.disabled" :active="item.active" :boxed="item.boxed" :class="item.class"
        @click.stop.prevent="onItemClick(item)" />
    </template>

    <slot />
  </v-list>
</template>
