<template>
  <div
    v-bind="$attrs"
    class="relative w-full shrink-0 bg-white dark:bg-zinc-950"
    :class="footerPaddingClass"
  >
    <BaseMenu
      v-model="showMenu"
      :items="menuEntries"
      :location="menuLocation"
      :offset="8"
      transition="scale-transition"
      :width="menuWidth"
      :full-width="menuFullWidth"
      :close-on-content-click="true"
      list-class="py-1"
      @select="onMenuSelect"
    >
      <template #activator="{ props: menuProps }">
        <BaseMenuList plain full-width tone="menu" list-class="pa-0 w-full bg-transparent">
          <BaseMenuListItem
            v-bind="menuProps"
            tone="menu"
            :class="activatorItemClass"
            :aria-label="$t('sidebar.userMenu.open')"
          >
            <template #leading>
              <v-avatar :color="avatarColor" size="38" class="shrink-0" theme="dark">
                <img
                  v-if="user.avatarUrl"
                  :src="user.avatarUrl"
                  :alt="user.name"
                  class="h-full w-full object-cover"
                />
                <span v-else class="text-xs font-bold text-white">{{ initials }}</span>
              </v-avatar>
            </template>
            <template v-if="showProfileText">
              <span class="truncate text-sm font-semibold text-high-emphasis dark:text-zinc-100">{{
                user.name
              }}</span>
              <span
                v-if="user.plan"
                class="mt-0.5 truncate text-xs text-medium-emphasis dark:text-zinc-400"
              >
                {{ user.plan }}
              </span>
            </template>
          </BaseMenuListItem>
        </BaseMenuList>
      </template>

      <template #prepend>
        <BaseMenuListItem tone="menu" disabled class="mx-0 cursor-default opacity-100">
          <template #leading>
            <v-avatar :color="avatarColor" size="38" class="shrink-0" theme="dark">
              <img
                v-if="user.avatarUrl"
                :src="user.avatarUrl"
                :alt="user.name"
                class="h-full w-full object-cover"
              />
              <span v-else class="text-xs font-bold text-white">{{ initials }}</span>
            </v-avatar>
          </template>
          <span class="truncate text-sm font-semibold text-high-emphasis dark:text-zinc-100">{{
            user.name
          }}</span>
          <span
            v-if="user.email"
            class="mt-0.5 truncate text-xs text-medium-emphasis dark:text-zinc-400"
          >
            {{ user.email }}
          </span>
        </BaseMenuListItem>
        <v-divider class="my-1 border-current/25" />
      </template>
    </BaseMenu>

    <BaseConfirmDialog v-model="showLogoutDialog" preset="logout" @confirm="onLogoutConfirmed" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useUiStore, type SidebarMode } from '~/stores/ui.store';
import { useSidebarUserMenu } from '~/composables/sidebar/useSidebarUserMenu';
import type { TooltipLocation } from '~/types/ui-menu';

defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    mode?: SidebarMode;
  }>(),
  {
    mode: 'desktop',
  },
);

const uiStore = useUiStore();
const isMobileMode = computed(() => props.mode === 'mobile');
const showProfileText = computed(() => uiStore.showSidebarExpandedActions(props.mode));
const isRailMode = computed(() => !isMobileMode.value && !showProfileText.value);

const menuLocation = computed<TooltipLocation>(() =>
  isRailMode.value ? 'end' : 'top start',
);

const menuFullWidth = computed(() => isMobileMode.value || showProfileText.value);
const menuWidth = computed(() => (isMobileMode.value ? '100%' : 225));

const footerPaddingClass = computed(() => {
  if (isMobileMode.value) {
    return 'px-4 pt-3 pb-[max(12px,env(safe-area-inset-bottom))]';
  }
  return showProfileText.value ? 'px-4 py-3' : 'px-2 py-3';
});

const activatorItemClass = computed(() =>
  [
    '!mx-0 w-full transition-colors',
    showProfileText.value
      ? 'min-h-[52px] rounded-xl border border-gray-200 bg-white px-2 py-2 hover:!bg-gray-100 dark:border-zinc-700 dark:bg-zinc-950 dark:hover:!bg-zinc-900'
      : 'justify-center px-0 hover:!bg-gray-100 dark:hover:!bg-zinc-900',
  ].join(' '),
);

const {
  avatarColor,
  initials,
  menuEntries,
  onMenuSelect,
  onLogoutConfirmed,
  showLogoutDialog,
  showMenu,
  user,
} = useSidebarUserMenu();
</script>
