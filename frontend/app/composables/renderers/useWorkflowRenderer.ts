import { ref, computed } from 'vue';
import {
  LucideCheckCircle2,
  LucideCircle,
  LucideLoader2,
  LucideAlertCircle,
} from 'lucide-vue-next';
import type { UseWorkflowRendererProps, WorkflowData } from '~/types/message';
import { useAnimStaggerReveal } from '../common/useAnimStaggerReveal';
import { useRenderAnimation } from '../common/useRenderAnimation';


export function useWorkflowRenderer(props: UseWorkflowRendererProps) {
  const anim = useRenderAnimation();
  const expandedSteps = ref<Record<number, boolean>>({});

  const data = computed<WorkflowData>(() => {
    const content = props.block.content;
    if (
      content &&
      typeof content === 'object' &&
      Array.isArray((content as Partial<WorkflowData>).steps)
    ) {
      return content as WorkflowData;
    }
    return { steps: [] };
  });

  const steps = computed(() => data.value.steps ?? []);
  const { visibleItems: visibleSteps } = useAnimStaggerReveal({
    items: steps,
    enabled: computed(() => Boolean(props.animate)),
    animId: computed(() => props.animId),
    intervalMs: anim.workflowStepMs,
    initialVisible: 1,
    maxVisible: anim.maxStaggerItems,
  });

  const toggleStep = (index: number) => {
    expandedSteps.value[index] = !expandedSteps.value[index];
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'complete':
        return LucideCheckCircle2;
      case 'active':
        return LucideLoader2;
      case 'error':
        return LucideAlertCircle;
      default:
        return LucideCircle;
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'complete':
        return 'text-emerald-500';
      case 'active':
        return 'text-blue-500 animate-spin';
      case 'error':
        return 'text-red-500';
      default:
        return 'text-zinc-300 dark:text-zinc-600';
    }
  };

  return {
    data,
    visibleSteps,
    expandedSteps,
    toggleStep,
    getStatusIcon,
    getStatusColor,
  };
}
