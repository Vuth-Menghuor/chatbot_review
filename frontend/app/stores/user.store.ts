import { defineStore } from 'pinia';
import { ref } from 'vue';
import { useAuthStore } from '~/stores/auth.store';

export interface UserProfile {
  name: string;
  nickname: string;
  email: string;
  phone: string;
  address: string;
  plan: string;
}

const DEFAULT_PROFILE: UserProfile = {
  name: 'User',
  nickname: '',
  email: '',
  phone: '',
  address: '',
  plan: '',
};

export const useUserStore = defineStore('user', () => {
  const avatarUrl = ref<string | undefined>(undefined);
  const name = ref<string>(DEFAULT_PROFILE.name);
  const nickname = ref<string>(DEFAULT_PROFILE.nickname);
  const email = ref<string>(DEFAULT_PROFILE.email);
  const phone = ref<string>(DEFAULT_PROFILE.phone);
  const address = ref<string>(DEFAULT_PROFILE.address);
  const plan = ref<string>(DEFAULT_PROFILE.plan);

  function persistProfile() {
    try {
      localStorage.setItem(
        'userProfile',
        JSON.stringify({
          name: name.value,
          nickname: nickname.value,
          email: email.value,
          phone: phone.value,
          address: address.value,
          plan: plan.value,
        }),
      );
    } catch {
      // ignore storage errors
    }
  }

  function setAvatar(url?: string) {
    avatarUrl.value = url;
    try {
      if (url) {
        localStorage.setItem('userAvatar', url);
      } else {
        localStorage.removeItem('userAvatar');
      }
    } catch {
      // ignore storage errors
    }
  }

  function setProfile(profile: Partial<UserProfile>) {
    if (profile.name !== undefined) name.value = profile.name;
    if (profile.nickname !== undefined) nickname.value = profile.nickname;
    if (profile.email !== undefined) email.value = profile.email;
    if (profile.phone !== undefined) phone.value = profile.phone;
    if (profile.address !== undefined) address.value = profile.address;
    if (profile.plan !== undefined) plan.value = profile.plan;
    persistProfile();
  }

  function syncFromAuthUser() {
    const authStore = useAuthStore();
    const user = authStore.user;
    if (!user) return;

    name.value = user.full_name;
    nickname.value = user.email.split('@')[0] ?? '';
    email.value = user.email;
    plan.value = user.role;
    persistProfile();
  }

  async function initFromLocalStorage() {
    try {
      const savedAvatar = localStorage.getItem('userAvatar');
      if (savedAvatar) avatarUrl.value = savedAvatar;

      const savedProfile = localStorage.getItem('userProfile');
      if (savedProfile) {
        const profile = JSON.parse(savedProfile) as Partial<UserProfile>;
        if (profile.name) name.value = profile.name;
        if (profile.nickname) nickname.value = profile.nickname;
        if (profile.email) email.value = profile.email;
        if (profile.phone) phone.value = profile.phone;
        if (profile.address) address.value = profile.address;
        if (profile.plan) plan.value = profile.plan;
      }

      const authStore = useAuthStore();
      if (!authStore.initialized) await authStore.init();
      syncFromAuthUser();
    } catch {
      // Keep a neutral profile if the API layer is temporarily unavailable.
    }
  }

  return {
    avatarUrl,
    name,
    nickname,
    email,
    phone,
    address,
    plan,
    setAvatar,
    setProfile,
    syncFromAuthUser,
    initFromLocalStorage,
  };
});
