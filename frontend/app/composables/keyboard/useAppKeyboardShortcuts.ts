import { onMounted, onUnmounted } from 'vue';
import { navigateTo } from '#imports';
import { useUiStore } from '~/stores/ui.store';

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || el.isContentEditable;
}

function hasModifier(e: KeyboardEvent): boolean {
  return e.metaKey || e.ctrlKey;
}

export function useAppKeyboardShortcuts() {
  const uiStore = useUiStore();

  function onKeyDown(e: KeyboardEvent) {
    const key = e.key.toLowerCase();
    const mod = hasModifier(e);

    if (key === 'escape') return;

    if (mod && key === 'k') {
      e.preventDefault();
      uiStore.openSearchDialog();
      return;
    }

    if (isEditableTarget(e.target) && !mod) return;

    if (mod && e.shiftKey && key === 'n') {
      e.preventDefault();
      uiStore.closeMobileSidebar();
      navigateTo('/');
      return;
    }

    if (mod && key === 'b') {
      e.preventDefault();
      uiStore.toggleSidebar();
      return;
    }

    if (mod && key === ',') {
      e.preventDefault();
      uiStore.openSettingsDialog('general');
      return;
    }

    if (mod && key === '/') {
      e.preventDefault();
      uiStore.openSettingsDialog('keyboard');
    }
  }

  onMounted(() => {
    if (!import.meta.client) return;
    window.addEventListener('keydown', onKeyDown);
  });

  onUnmounted(() => {
    if (!import.meta.client) return;
    window.removeEventListener('keydown', onKeyDown);
  });
}
