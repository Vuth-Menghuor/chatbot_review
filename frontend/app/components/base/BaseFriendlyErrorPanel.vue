<script setup lang="ts">
import { ref, type Component } from 'vue';
import { LucideRotateCcw, LucideAlertCircle } from 'lucide-vue-next';

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
      'border-slate-200/90 bg-gradient-to-br from-slate-50 to-slate-100/80 dark:border-slate-600 dark:from-slate-900/60 dark:to-slate-950/40',
    iconWrapClass: 'bg-slate-200/80 text-slate-700 dark:bg-slate-800 dark:text-slate-200',
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
    class="friendly-error-panel my-3 w-full rounded-2xl border shadow-sm"
    :class="props.shellClass"
  >
    <v-card-text class="pa-4 pa-sm-5">
      <div class="d-flex gap-4">
        <v-sheet
          height="44"
          width="44"
          rounded="lg"
          class="d-flex align-center justify-center shrink-0 mt-1"
          :class="props.iconWrapClass"
        >
          <component :is="props.iconComponent" class="h-5 w-5" stroke-width="2" />
        </v-sheet>

        <div class="min-w-0 flex-1">
          <v-card-title
            tag="h3"
            class="text-wrap pa-0 text-base font-weight-semibold leading-snug tracking-tight"
            :class="titleClass"
          >
            {{ title }}
          </v-card-title>

          <p class="mt-2 mb-0 text-sm leading-relaxed sm:text-[15px]" :class="bodyClass">
            {{ message }}
          </p>

          <div v-if="technicalDetails" class="mt-3">
            <v-btn
              variant="text"
              density="compact"
              class="px-0 h-auto min-h-0 text-none text-xs font-weight-medium text-slate-500 dark:text-slate-400"
              @click="detailsOpen = !detailsOpen"
            >
              {{ detailsOpen ? technicalDetailsHideLabel : technicalDetailsLabel }}
            </v-btn>
            <v-expand-transition>
              <v-sheet
                v-show="detailsOpen"
                rounded="lg"
                class="mt-2 border border-black/6 bg-white/50 pa-3 dark:border-white/10 dark:bg-black/20"
              >
                <pre
                  class="mb-0 max-h-32 overflow-auto whitespace-pre-wrap wrap-break-word font-mono text-[11px] leading-relaxed text-slate-600 dark:text-slate-400"
                  >{{ technicalDetails }}</pre
                >
              </v-sheet>
            </v-expand-transition>
          </div>

          <v-btn
            v-if="retryable"
            variant="outlined"
            color="primary"
            size="small"
            class="mt-4 rounded-lg text-none font-weight-medium"
            :prepend-icon="LucideRotateCcw"
            @click="emit('retry')"
          >
            {{ retryLabel }}
          </v-btn>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>
