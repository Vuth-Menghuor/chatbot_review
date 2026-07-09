import { nextTick, onMounted, onUnmounted, ref, watch, type Ref } from 'vue';

const SPY_SELECTOR = '[data-settings-spy]';

export function useSettingsScrollSpy(scrollRoot: Ref<HTMLElement | null>, headerOffset = 72) {
  const activeSpyId = ref<string | null>(null);

  let observer: IntersectionObserver | null = null;

  function disconnect() {
    observer?.disconnect();
    observer = null;
  }

  function reset() {
    disconnect();
    activeSpyId.value = null;
  }

  function refresh() {
    disconnect();

    const root = scrollRoot.value;
    if (!root) {
      activeSpyId.value = null;
      return;
    }

    const blocks = root.querySelectorAll<HTMLElement>(SPY_SELECTOR);
    if (!blocks.length) {
      activeSpyId.value = null;
      return;
    }

    const tops = new Map<string, number>();

    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const id = entry.target.getAttribute('data-settings-spy');
          if (!id) continue;

          if (entry.isIntersecting) {
            tops.set(id, entry.boundingClientRect.top);
          } else {
            tops.delete(id);
          }
        }

        if (tops.size === 0) {
          activeSpyId.value = blocks[0]?.getAttribute('data-settings-spy') ?? null;
          return;
        }

        activeSpyId.value = [...tops.entries()].sort((a, b) => a[1] - b[1])[0]?.[0] ?? null;
      },
      {
        root,
        rootMargin: `-${headerOffset}px 0px -45% 0px`,
        threshold: [0, 0.01, 0.1, 0.25, 0.5, 1],
      },
    );

    blocks.forEach((block) => observer?.observe(block));
    activeSpyId.value = blocks[0]?.getAttribute('data-settings-spy') ?? null;
  }

  watch(scrollRoot, () => nextTick(refresh));

  onMounted(() => nextTick(refresh));
  onUnmounted(disconnect);

  return { activeSpyId, refreshSpy: refresh, resetSpy: reset };
}
