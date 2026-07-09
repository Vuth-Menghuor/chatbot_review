import { computed, type Component, type Ref } from 'vue';
import {
  LucideAlertCircle,
  LucideAlertTriangle,
  LucideClock,
  LucideServerCrash,
  LucideWifiOff,
} from 'lucide-vue-next';
import type { MessageBlock } from '~/types/message';

/** Classifies errors for copy and icon selection. */
export type ErrorDisplayKind = 'network' | 'timeout' | 'rate_limit' | 'server' | 'generic';

const KIND_SHELL: Record<ErrorDisplayKind, string> = {
  network:
    'border-amber-200/90 bg-gradient-to-br from-amber-50 to-amber-100/70 dark:border-amber-900/50 dark:from-amber-950/40 dark:to-amber-900/20',
  timeout:
    'border-orange-200/90 bg-gradient-to-br from-orange-50 to-orange-100/70 dark:border-orange-900/50 dark:from-orange-950/40 dark:to-orange-900/20',
  rate_limit:
    'border-violet-200/90 bg-gradient-to-br from-violet-50 to-violet-100/70 dark:border-violet-900/50 dark:from-violet-950/40 dark:to-violet-900/20',
  server:
    'border-red-200/90 bg-gradient-to-br from-red-50 to-red-100/70 dark:border-red-900/50 dark:from-red-950/40 dark:to-red-900/20',
  generic:
    'border-slate-200/90 bg-gradient-to-br from-slate-50 to-slate-100/80 dark:border-slate-600 dark:from-slate-900/60 dark:to-slate-950/40',
};

const KIND_ICON_WRAP: Record<ErrorDisplayKind, string> = {
  network: 'bg-amber-200/80 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200',
  timeout: 'bg-orange-200/80 text-orange-800 dark:bg-orange-900/50 dark:text-orange-200',
  rate_limit: 'bg-violet-200/80 text-violet-800 dark:bg-violet-900/50 dark:text-violet-200',
  server: 'bg-red-200/80 text-red-800 dark:bg-red-900/50 dark:text-red-200',
  generic: 'bg-slate-200/80 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
};

const KIND_ICONS: Record<ErrorDisplayKind, Component> = {
  network: LucideWifiOff,
  timeout: LucideClock,
  rate_limit: LucideAlertTriangle,
  server: LucideServerCrash,
  generic: LucideAlertCircle,
};

function classifyErrorSignal(text: string): ErrorDisplayKind {
  const t = text.toLowerCase();

  if (/\b(429|rate limit|too many requests)\b/.test(t)) return 'rate_limit';
  if (/\b(timeout|timed out|etimedout)\b/.test(t)) return 'timeout';
  if (
    /\b(500|502|503|504|bad gateway|service unavailable|gateway timeout|internal server|econnrefused|eai_again)\b/.test(
      t,
    )
  ) {
    return 'server';
  }
  if (
    /\b(failed to fetch|networkerror|network request failed|load failed|offline|internet disconnected|err_network|enotfound|net::err_|err_internet|err_connection|socket hang up|tls|cors policy|fetch failed)\b/.test(
      t,
    ) ||
    (/\bfetch\b/.test(t) && /\b(fail|error|abort)\b/.test(t))
  ) {
    return 'network';
  }

  return 'generic';
}

export function useFriendlyErrorDisplay(errorKind?: Ref<ErrorDisplayKind>) {
  const kind = computed(() => errorKind?.value ?? 'generic');

  return {
    shellClass: computed(() => KIND_SHELL[kind.value]),
    iconWrapClass: computed(() => KIND_ICON_WRAP[kind.value]),
    titleClass: computed(() => 'text-slate-900 dark:text-slate-100'),
    bodyClass: computed(() => 'text-slate-600 dark:text-slate-300'),
    iconComponent: computed<Component>(() => KIND_ICONS[kind.value]),
  };
}

export function useErrorRenderer(block: MessageBlock) {
  const { t } = useI18n();

  const content = computed(() =>
    block.content && typeof block.content === 'object'
      ? (block.content as Record<string, unknown>)
      : {},
  );

  const errorTitle = computed(() => {
    const title = content.value.title;
    if (typeof title === 'string' && title.trim()) return title;

    if (typeof block.content === 'string' && block.content.trim()) {
      return t('error.genericTitle');
    }

    return t('error.genericTitle');
  });

  const errorMessage = computed(() => {
    if (typeof block.content === 'string' && block.content.trim()) return block.content;

    const message = content.value.message;
    if (typeof message === 'string') return message;
    if (message && typeof message === 'object') {
      const nested = (message as Record<string, unknown>).message;
      return typeof nested === 'string' ? nested : t('error.genericBody');
    }
    return t('error.genericBody');
  });

  const errorDetail = computed(() => {
    const detail = content.value.detail ?? content.value.details ?? content.value.code;
    return typeof detail === 'string' && detail.trim() ? detail : '';
  });

  const retryable = computed(() => Boolean(content.value.retryable));

  const explicitKind = computed((): ErrorDisplayKind | null => {
    const k = content.value.kind ?? content.value.category;
    if (typeof k !== 'string') return null;
    if (k === 'network' || k === 'timeout' || k === 'rate_limit' || k === 'server') return k;
    if (k === 'generic') return 'generic';
    return null;
  });

  const errorKind = computed((): ErrorDisplayKind => {
    if (explicitKind.value) return explicitKind.value;
    const signal = [
      errorTitle.value,
      errorMessage.value,
      errorDetail.value,
      typeof content.value.code === 'string' ? content.value.code : '',
    ].join(' ');
    return classifyErrorSignal(signal);
  });

  const friendlyDisplay = useFriendlyErrorDisplay(errorKind);

  const headline = computed(() => {
    switch (errorKind.value) {
      case 'network':
        return t('error.network.title');
      case 'timeout':
        return t('error.timeout.title');
      case 'rate_limit':
        return t('error.rateLimit.title');
      case 'server':
        return t('error.server.title');
      default: {
        const title = errorTitle.value;
        if (title === t('error.genericTitle')) return title;
        return title;
      }
    }
  });

  const body = computed(() => {
    switch (errorKind.value) {
      case 'network':
        return t('error.network.body');
      case 'timeout':
        return t('error.timeout.body');
      case 'rate_limit':
        return t('error.rateLimit.body');
      case 'server':
        return t('error.server.body');
      default:
        return errorMessage.value;
    }
  });

  const technicalHint = computed(() => {
    const parts: string[] = [];
    const raw = errorMessage.value?.trim();
    const friendlyKinds: ErrorDisplayKind[] = ['network', 'timeout', 'rate_limit', 'server'];
    if (friendlyKinds.includes(errorKind.value) && raw && raw !== body.value) {
      parts.push(raw);
    }
    if (errorDetail.value && !parts.includes(errorDetail.value)) {
      parts.push(errorDetail.value);
    }
    const code = content.value.code;
    if (typeof code === 'string' && code.trim() && code !== errorDetail.value) {
      parts.push(`${t('error.codeLabel')}: ${code.trim()}`);
    }
    return parts.filter(Boolean).join('\n\n');
  });

  const retryLabel = computed(() =>
    ['network', 'timeout', 'rate_limit', 'server'].includes(errorKind.value)
      ? t('error.tryAgain')
      : t('error.regenerate'),
  );

  return {
    errorTitle,
    errorMessage,
    errorDetail,
    retryable,
    errorKind,
    headline,
    body,
    technicalHint,
    retryLabel,
    friendlyDisplay,
  };
}
