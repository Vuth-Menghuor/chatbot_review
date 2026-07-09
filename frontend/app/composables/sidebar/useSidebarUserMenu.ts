import { computed, ref } from 'vue';
import { navigateTo } from '#imports';
import { useAuthStore } from '~/stores/auth.store';
import { useUserStore } from '~/stores/user.store';
import { useAppLocale } from '~/composables/common/useAppLocale';
import { useUiStore } from '~/stores/ui.store';
import type { SettingsSectionId } from '~/types/settings-nav';
import type { MenuEntry, MenuItem, SubmenuItem } from '~/types/ui-menu';
import { getInitials } from '~/utils/user';

export interface SidebarUser {
  name: string;
  plan: string;
  email?: string;
  avatarUrl?: string;
}

export function useSidebarUserMenu() {
  const authStore = useAuthStore();
  const userStore = useUserStore();
  const { t } = useAppLocale();
  const uiStore = useUiStore();
  userStore.initFromLocalStorage();

  const avatarColor = '#e8725a';
  const showMenu = ref(false);
  const showLogoutDialog = ref(false);

  const user = computed<SidebarUser>(() => ({
    name: userStore.name,
    plan:
      userStore.plan === 'Admin' ? t('sidebar.userMenu.roleAdmin') : userStore.plan,
    email: userStore.email,
    avatarUrl: userStore.avatarUrl,
  }));

  const initials = computed(() => getInitials(user.value.name));

  function closeMenu() {
    showMenu.value = false;
  }

  function openSettings(section: SettingsSectionId) {
    uiStore.openSettingsDialog(section);
    closeMenu();
  }

  function onLogoutClick() {
    uiStore.closeMobileSidebar();
    showLogoutDialog.value = true;
    closeMenu();
  }

  function onMenuSelect(item: MenuItem | SubmenuItem) {
    if (item.value === 'account') {
      openSettings('account');
      return;
    }

    if (item.value === 'settings') {
      openSettings('general');
      return;
    }

    if (item.value === 'logout') {
      onLogoutClick();
    }
  }

  const menuEntries = computed<MenuEntry[]>(() => [
    {
      type: 'item',
      value: 'account',
      labelKey: 'sidebar.userMenu.account',
      icon: 'lucide-circle-user',
    },
    {
      type: 'item',
      value: 'settings',
      labelKey: 'sidebar.userMenu.settings',
      icon: 'lucide-settings',
    },
    { type: 'divider' },
    {
      type: 'item',
      value: 'logout',
      labelKey: 'sidebar.userMenu.logout',
      icon: 'lucide-log-out',
      danger: true,
    },
  ]);

  async function onLogoutConfirmed() {
    await authStore.logout();
    await navigateTo('/login');
  }

  return {
    avatarColor,
    initials,
    menuEntries,
    onMenuSelect,
    onLogoutConfirmed,
    showLogoutDialog,
    showMenu,
    user,
  };
}
