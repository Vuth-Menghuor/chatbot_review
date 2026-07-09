import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue';
import { storeToRefs } from 'pinia';
import { usePreferencesStore } from '~/stores/preferences.store';
import type { Message } from '~/types/message';

/**
 * useChatList — UI logic for the scrollable message list
 */
export function useChatList(
  props: { messages: Message[]; loading?: boolean },
  emit: (e: 'scroll-status', payload: { isAtBottom: boolean }) => void,
) {
  const preferencesStore = usePreferencesStore();
  const { autoScrollMessages } = storeToRefs(preferencesStore);
  const scrollContainer = ref<HTMLElement | null>(null);
  const isAtBottom = ref(true);

  const setAtBottom = (value: boolean) => {
    if (isAtBottom.value === value) return;
    isAtBottom.value = value;
    emit('scroll-status', { isAtBottom: isAtBottom.value });
  };

  const scrollToBottom = async (behavior: ScrollBehavior = 'smooth') => {
    if (!scrollContainer.value) return;
    await nextTick();
    const el = scrollContainer.value;
    el.scrollTo({
      top: el.scrollHeight,
      behavior,
    });
    // Never assume we're at bottom — `setAtBottom(true)` here fought users who scroll up while
    // streaming (smooth scroll + reactive updates left `isAtBottom` stuck true).
    if (behavior === 'instant' || behavior === 'auto') {
      handleScroll();
    } else {
      const sync = () => handleScroll();
      el.addEventListener('scrollend', sync, { once: true });
      window.setTimeout(sync, 450);
    }
  };

  const scrollToBottomInstantly = async () => {
    await nextTick();
    await new Promise((resolve) => requestAnimationFrame(resolve));
    if (!scrollContainer.value) return;
    const el = scrollContainer.value;
    el.scrollTop = el.scrollHeight;
    handleScroll();
  };

  const handleScroll = () => {
    if (!scrollContainer.value) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value;
    const atBottom = scrollHeight - (scrollTop + clientHeight) < 120;
    setAtBottom(atBottom);
  };

  // Auto-scroll only when the user is already near the bottom.
  // Use instant scroll so `handleScroll()` sees the real position (smooth + setAtBottom was sticky).
  watch(
    [() => props.messages, () => props.loading],
    async () => {
      if (!autoScrollMessages.value) return;
      if (!scrollContainer.value) return;
      if (!isAtBottom.value) return;
      await scrollToBottom('instant');
    },
    { deep: true },
  );

  // When opening another saved chat, jump straight to the latest message.
  watch(
    () => props.messages[0]?.id,
    async () => {
      if (!autoScrollMessages.value) return;
      await scrollToBottomInstantly();
    },
  );

  onMounted(() => {
    if (autoScrollMessages.value) {
      scrollToBottomInstantly();
    }
    scrollContainer.value?.addEventListener('scroll', handleScroll);
  });

  onUnmounted(() => {
    scrollContainer.value?.removeEventListener('scroll', handleScroll);
  });

  return {
    scrollContainer,
    isAtBottom,
    scrollToBottom,
    scrollToBottomInstantly,
  };
}
