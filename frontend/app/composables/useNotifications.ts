import { computed } from 'vue';

export type Notifications = {
  completions?: boolean;
  [key: string]: unknown;
};

export function useNotifications(
  props: { notifications?: Notifications },
  emit: (e: string, ...args: unknown[]) => void,
) {
  const completions = computed<boolean>({
    get: () => !!props.notifications?.completions,
    set: (v: boolean) => emit('update:notifications', { ...props.notifications, completions: v }),
  });

  return { completions };
}
