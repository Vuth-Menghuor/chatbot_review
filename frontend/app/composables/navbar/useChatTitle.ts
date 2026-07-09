import { computed } from 'vue';
import { useChatStore } from '~/stores/chat.store';
import { useProjectStore } from '~/stores/project.store';
import { useAppLocale } from '~/composables/common/useAppLocale';
import { useNavbarRouteContext } from './useRouteContext';

export function useNavbarChatTitle() {
  const { route, isChatPage, isProjectPage, isSettingsPage } = useNavbarRouteContext();
  const chatStore = useChatStore();
  const projectStore = useProjectStore();
  const { t, locale } = useAppLocale();

  const displayTitle = computed(() => {
    void locale.value;

    if (isSettingsPage.value) return t('settings.title');

    if (isProjectPage.value) {
      const project = projectStore.projects.find((p) => p.id === route.params.id);
      return project ? project.name : t('project.defaultTitle');
    }

    if (isChatPage.value) {
      const chat = chatStore.recentChats.find((c) => c.id === route.params.id);
      return chat ? chat.title : t('chat.defaultTitle');
    }

    return t('chat.newChat');
  });

  return { displayTitle };
}
