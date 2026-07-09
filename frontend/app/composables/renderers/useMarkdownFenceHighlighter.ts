import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue';
import { highlightCode } from '~/utils/code';

export function useMarkdownFenceHighlighter(
  containerRef: Ref<HTMLElement | null>,
  isDark: Ref<boolean>,
  trigger: Ref<unknown>,
) {
  let runId = 0;

  async function hydrateFences() {
    const id = ++runId;
    await nextTick();
    const root = containerRef.value;
    if (!root) return;

    const fences = root.querySelectorAll<HTMLElement>(
      '.markdown-code-fence[data-fence-code]:not([data-shiki-done])',
    );

    await Promise.all(
      Array.from(fences).map(async (fence) => {
        const lang = fence.dataset.fenceLang ?? 'text';
        let code = fence.dataset.fenceCode ?? '';
        try {
          code = decodeURIComponent(code);
        } catch {
          /* keep raw */
        }
        const wrap = fence.querySelector<HTMLElement>('.shiki-markdown-wrap');
        if (!wrap || !code) return;

        wrap.classList.add('opacity-60');
        const html = await highlightCode(code, lang, isDark.value ? 'dark' : 'light');
        if (id !== runId) return;

        wrap.innerHTML = html.replace(
          /background-color:\s*#[0-9a-fA-F]+;?/g,
          'background-color: transparent;',
        );
        wrap.classList.remove('opacity-60');
        fence.dataset.shikiDone = 'true';
      }),
    );
  }

  const stop = watch([containerRef, isDark, trigger], () => hydrateFences(), { flush: 'post' });

  onBeforeUnmount(() => {
    runId += 1;
    stop();
  });

  return { hydrateFences };
}
