import { computed } from 'vue';
import {
  CopyIcon,
  CheckIcon,
  PencilIcon,
  RefreshCwIcon,
  ThumbsDownIcon,
  ThumbsUpIcon,
  BookOpenIcon,
} from 'lucide-vue-next';
import type { ChatActionItem, ChatActionType, Message, UseChatActionEmit } from '~/types/message';
import { useUiStore } from '~/stores/ui.store';
import { useClipboardCopy } from '~/composables/common/useClipboardCopy';

const ACTION_BUTTON_CLASS =
  'text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-300 hover:bg-neutral-100/70 dark:hover:bg-neutral-800/60';

export function useChatAction(props: { message: Message }, emit: UseChatActionEmit) {
  const { t } = useI18n();
  const uiStore = useUiStore();
  // LAN testing commonly uses HTTP, where navigator.clipboard is unavailable.
  // Enable the DOM-based fallback so the chat action remains usable there.
  const { copied, copyText } = useClipboardCopy({ fallbackToTextarea: true });

  const hasSources = computed(() => (props.message.sources?.length ?? 0) > 0);

  const actions = computed<ChatActionItem[]>(() => {
    const isAssistant = props.message.role === 'assistant';

    if (isAssistant) {
      const baseActions: ChatActionItem[] = [
        {
          icon: copied.value ? CheckIcon : CopyIcon,
          tooltip: copied.value ? t('common.copied') : t('common.copy'),
          action: 'copy',
        },
        { icon: ThumbsUpIcon, tooltip: t('chat.actions.like'), action: 'like' },
        { icon: ThumbsDownIcon, tooltip: t('chat.actions.dislike'), action: 'dislike' },
        { icon: RefreshCwIcon, tooltip: t('chat.actions.regenerate'), action: 'regenerate' },
      ];
      if (hasSources.value) {
        baseActions.push({
          icon: BookOpenIcon,
          tooltip: t('chat.actions.sources', { count: props.message.sources!.length }),
          action: 'sources',
        });
      }
      return baseActions;
    }

    return [
      {
        icon: copied.value ? CheckIcon : CopyIcon,
        tooltip: copied.value ? t('common.copied') : t('common.copy'),
        action: 'copy',
      },
      { icon: PencilIcon, tooltip: t('chat.actions.edit'), action: 'edit' },
    ];
  });

  const handleAction = async (action: ChatActionType) => {
    const messageId = props.message.id || '';
    switch (action) {
      case 'copy': {
        const success = await copyText(props.message.content);
        if (success) emit('copy', props.message.content);
        break;
      }
      case 'like':
        emit('like', messageId);
        break;

      case 'dislike':
        emit('dislike', messageId);
        break;
      case 'regenerate':
        emit('regenerate', messageId);
        break;
      case 'edit':
        emit('edit', messageId);
        break;
      case 'sources':
        uiStore.openSourcesPanel(props.message);
        break;
    }
  };

  const getButtonClass = (action: ChatActionType) => {
    const isActive =
      (action === 'like' && props.message.feedback === 'like') ||
      (action === 'dislike' && props.message.feedback === 'dislike');

    return [ACTION_BUTTON_CLASS, isActive ? '!text-blue-600 dark:!text-blue-400' : ''].join(' ');
  };

  return {
    actions,
    handleAction,
    getButtonClass,
  };
}
