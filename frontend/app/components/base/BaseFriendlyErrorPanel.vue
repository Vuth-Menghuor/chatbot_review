<script setup lang="ts">
import { ref, type Component } from 'vue';
import { LucideChevronDown, LucideRotateCcw, LucideAlertCircle } from 'lucide-vue-next';

const props = withDefaults(
  defineProps<{
    title: string;
    message: string;
    /** Shown behind a Vuetify expand transition (optional). */
    technicalDetails?: string;
    retryable?: boolean;
    retryLabel?: string;
    technicalDetailsLabel?: string;
    technicalDetailsHideLabel?: string;
    shellClass?: string;
    iconWrapClass?: string;
    iconComponent?: Component;
  }>(),
  {
    technicalDetails: '',
    retryable: false,
    retryLabel: 'Try again',
    technicalDetailsLabel: 'Technical details',
    technicalDetailsHideLabel: 'Hide details',
    shellClass:
      'border-slate-200 bg-white dark:border-slate-800 dark:bg-zinc-950',
    iconWrapClass: 'bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-200',
    iconComponent: LucideAlertCircle,
  },
);

const emit = defineEmits<{
  retry: [];
}>();

const detailsOpen = ref(false);

const titleClass = 'text-slate-900 dark:text-slate-100';
const bodyClass = 'text-slate-600 dark:text-slate-300';

</script>

<template>
  <v-card
    role="alert"
    variant="flat"
    :elevation="0"
    class="friendly-error-panel my-3 w-full overflow-hidden rounded-lg border shadow-sm"
    :class="props.shellClass"
  >
    <v-card-text class="pa-0">
      <div class="d-flex gap-3 pa-4">
        <v-sheet
          height="32"
          width="32"
          rounded="circle"
          class="d-flex align-center justify-center shrink-0 mt-0.5"
          :class="props.iconWrapClass"
        >
          <component :is="props.iconComponent" class="h-4 w-4" stroke-width="2.25" />
        </v-sheet>

        <div class="min-w-0 flex-1">
          <v-card-title
            tag="h3"
            class="text-wrap pa-0 text-sm font-weight-semibold leading-snug"
            :class="titleClass"
          >
            {{ title }}
          </v-card-title>

          <p class="mt-1 mb-0 text-sm leading-relaxed" :class="bodyClass">
            {{ message }}
          </p>

          <div v-if="retryable || technicalDetails" class="mt-4 flex flex-wrap items-center gap-2">
            <v-btn
              v-if="retryable"
              variant="flat"
              color="primary"
              size="small"
              class="rounded-lg text-none font-weight-semibold shadow-sm"
              :prepend-icon="LucideRotateCcw"
              @click="emit('retry')"
            >
              {{ retryLabel }}
            </v-btn>

            <v-btn
              v-if="technicalDetails"
              variant="text"
              density="comfortable"
              size="small"
              class="rounded-lg px-2 text-none text-xs font-weight-medium text-slate-500 dark:text-slate-400"
              :aria-expanded="detailsOpen"
              @click="detailsOpen = !detailsOpen"
            >
              {{ detailsOpen ? technicalDetailsHideLabel : technicalDetailsLabel }}
              <LucideChevronDown
                class="ml-1 h-3.5 w-3.5 transition-transform duration-200"
                :class="{ 'rotate-180': detailsOpen }"
                aria-hidden="true"
              />
            </v-btn>
          </div>

          <v-expand-transition>
            <v-sheet
              v-if="technicalDetails"
              v-show="detailsOpen"
              rounded="lg"
              class="mt-3 border border-black/6 bg-white/70 pa-3 dark:border-white/10 dark:bg-black/20"
            >
              <pre
                class="mb-0 max-h-32 overflow-auto whitespace-pre-wrap wrap-break-word font-mono text-[11px] leading-relaxed text-slate-600 dark:text-slate-400"
                >{{ technicalDetails }}</pre
              >
            </v-sheet>
          </v-expand-transition>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>
