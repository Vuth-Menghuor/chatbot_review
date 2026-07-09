<script setup lang="ts">
import { LucideChevronDown, LucideChevronUp } from 'lucide-vue-next';
import type { MessageBlock } from '~/types/message';
import { useWorkflowRenderer } from '~/composables/renderers/useWorkflowRenderer';

const props = defineProps<{
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}>();

const { data, visibleSteps, expandedSteps, toggleStep, getStatusIcon, getStatusColor } =
  useWorkflowRenderer(props);
</script>

<template>
  <BaseCard custom-class="rounded-lg w-full bg-white dark:bg-zinc-950 p-4">
    <div class="mb-3">
      <h3 class="text-sm font-semibold text-zinc-800 dark:text-zinc-100">
        {{ data?.title || data?.toolName || $t('workflow.title') }}
      </h3>
    </div>
    <TransitionGroup name="step-fade" tag="div" class="space-y-4">
      <div v-for="(step, index) in visibleSteps" :key="`${step.label}-${index}`" class="relative">
        <div
          v-if="index !== (data?.steps?.length ?? 0) - 1"
          class="absolute left-[13px] top-[28px] bottom-[-8px] w-[2px] bg-zinc-200 dark:bg-zinc-800"
        />
        <div class="flex gap-3">
          <div class="relative z-10 pt-1">
            <v-avatar
              size="30"
              class="bg-white border border-zinc-200 dark:bg-zinc-900 dark:border-zinc-800"
            >
              <component
                :is="getStatusIcon(step.status)"
                :size="18"
                :class="getStatusColor(step.status)"
                class="transition-colors duration-300"
              />
            </v-avatar>
          </div>
          <div class="flex-1">
            <div
              class="flex items-start justify-between gap-3 py-2 mb-2"
              :class="step.details ? 'cursor-pointer' : ''"
              @click="step.details ? toggleStep(index) : null"
            >
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span
                    class="text-sm font-semibold transition-colors"
                    :class="[
                      step.status === 'active'
                        ? 'text-blue-600 dark:text-blue-400'
                        : 'text-zinc-700 dark:text-zinc-300',
                      step.status === 'pending' ? 'opacity-50' : '',
                    ]"
                  >
                    {{ step.label }}
                  </span>
                </div>
              </div>
              <div v-if="step.details" class="text-zinc-400">
                <component
                  :is="expandedSteps[index] ? LucideChevronUp : LucideChevronDown"
                  :size="16"
                />
              </div>
            </div>
            <v-expand-transition name="expand">
              <div v-if="expandedSteps[index] && step.details">
                <div
                  class="text-sm text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap mt-2 leading-relaxed"
                >
                  {{ step.details }}
                </div>
              </div>
            </v-expand-transition>
          </div>
        </div>
      </div>
    </TransitionGroup>
  </BaseCard>
</template>
