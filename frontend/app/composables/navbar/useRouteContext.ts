import { computed } from 'vue';
import { useRoute } from '#imports';

/** Route flags shared by navbar chat title, more menu, and header shell. */
export function useNavbarRouteContext() {
  const route = useRoute();

  const isChatPage = computed(() => !!route.params.id && route.path.includes('/chat/'));
  const isProjectPage = computed(() => !!route.params.id && route.path.includes('/projects/'));
  const isSettingsPage = computed(() => route.path.includes('/settings'));

  return {
    route,
    isChatPage,
    isProjectPage,
    isSettingsPage,
  };
}
