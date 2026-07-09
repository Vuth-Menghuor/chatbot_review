import { defineNuxtPlugin } from '#app';
import { useAuthStore } from '~/stores/auth.store';

export default defineNuxtPlugin(async () => {
  const authStore = useAuthStore();
  if (!authStore.initialized) {
    await authStore.init();
  }
});
