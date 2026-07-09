import { defineNuxtRouteMiddleware, navigateTo } from '#app';
import { useAuthStore } from '~/stores/auth.store';

const PUBLIC_ROUTES = new Set(['/login', '/register']);

export default defineNuxtRouteMiddleware(async (to) => {
  const authStore = useAuthStore();

  if (!authStore.initialized) {
    await authStore.init();
  }

  const isPublicRoute = PUBLIC_ROUTES.has(to.path);

  if (isPublicRoute) {
    if (authStore.isAuthenticated) {
      return navigateTo('/');
    }
    return;
  }

  if (!authStore.isAuthenticated) {
    return navigateTo({
      path: '/login',
      query: to.fullPath !== '/' ? { redirect: to.fullPath } : undefined,
    });
  }
});
