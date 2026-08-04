import { defineStore } from 'pinia';
import { computed } from 'vue';
import { useAuthStore } from '~/stores/auth.store';

const DEFAULT_PROFILE = {
  name: 'User',
  nickname: '',
  email: '',
  phone: '',
  address: '',
  plan: '',
};

export const useUserStore = defineStore('user', () => {
  const authStore = useAuthStore();

  const name = computed(() => authStore.user?.full_name || DEFAULT_PROFILE.name);
  const email = computed(() => authStore.user?.email || DEFAULT_PROFILE.email);
  const nickname = computed(
    () => authStore.user?.nickname || email.value.split('@')[0] || DEFAULT_PROFILE.nickname,
  );
  const phone = computed(() => authStore.user?.phone || DEFAULT_PROFILE.phone);
  const address = computed(() => authStore.user?.address || DEFAULT_PROFILE.address);
  const avatarUrl = computed(() => authStore.user?.avatar_url || undefined);
  const plan = computed(() => authStore.user?.role || DEFAULT_PROFILE.plan);

  return {
    avatarUrl,
    name,
    nickname,
    email,
    phone,
    address,
    plan,
  };
});
