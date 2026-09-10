<script setup lang="ts">
import { computed } from 'vue';
import type { InteractionField, MessageBlock } from '~/types/message';
import { useInteractionRenderer } from '~/composables/renderers/useInteractionRenderer';

const props = defineProps<{ block: MessageBlock }>();
const emit = defineEmits<{
  (e: 'user-reply', payload: { requestId: string; toolName?: string; action: string; values: Record<string, unknown> }): void;
}>();

const { t } = useI18n();
const {
  data,
  fields,
  kind,
  values,
  isValid,
  submitted,
  submittedAction,
  summaryEntries,
  buildPayload,
  markSubmitted,
} = useInteractionRenderer(() => props.block);

const actions = computed(() =>
  Array.isArray(data.value.actions) && data.value.actions.length
    ? (data.value.actions as Array<{ id: string; label?: string; primary?: boolean }>)
    : kind.value === 'confirm'
      ? [
          { id: 'submit', label: t('common.confirm'), primary: true },
          { id: 'cancel', label: t('common.cancel') },
        ]
      : [{ id: 'submit', label: t('interaction.submit'), primary: true }],
);

const requestId = computed(() =>
  String(data.value.requestId ?? data.value.taskId ?? props.block.id),
);

function safeT(key: string, fallback: string) {
  const translated = t(key);
  return translated === key ? fallback : translated;
}

const answerPlaceholder = computed(() => safeT('interaction.answerPlaceholder', 'Type your answer'));

function fieldInvalid(field: InteractionField) {
  return field.required && submitted.value === false && !values[field.name];
}

function onFileChange(fieldName: string, files: File[] | File | null) {
  const file = Array.isArray(files) ? files[0] : files;
  values[fieldName] = file ?? null;
}

function handleAction(action: string) {
  if (submitted.value) return;
  const payload = action === 'cancel' ? {} : buildPayload(action);
  if (action !== 'cancel' && !isValid.value) return;
  markSubmitted(action, payload);
  emit('user-reply', {
    requestId: requestId.value,
    toolName: typeof data.value.toolName === 'string' ? data.value.toolName : undefined,
    action,
    values: payload,
  });
}
</script>

<template>
  <div
    class="my-1 w-full max-w-3xl rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950 sm:p-5"
    :aria-busy="!submitted && block.isComplete === false"
  >
    <div class="mb-5 border-b border-zinc-100 pb-4 dark:border-zinc-800">
      <h3 class="text-sm font-semibold leading-5 text-zinc-950 dark:text-zinc-50">
        {{ data.title || t('interaction.title') }}
      </h3>
      <p v-if="data.description" class="mt-1.5 whitespace-pre-line text-sm leading-6 text-zinc-600 dark:text-zinc-400">
        {{ data.description }}
      </p>
    </div>

    <div
      v-if="submitted"
      class="flex flex-col gap-4"
      role="status"
      aria-live="polite"
    >
      <p class="text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {{
          submittedAction === 'cancel'
            ? t('interaction.cancelled')
            : t('interaction.submitted')
        }}
      </p>
      <div v-if="summaryEntries.length" class="space-y-2">
        <div
          v-for="entry in summaryEntries"
          :key="entry.key"
          class="rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 text-sm dark:border-zinc-800 dark:bg-zinc-900/70"
        >
          <div class="font-medium leading-5 text-zinc-800 dark:text-zinc-100">
            {{ entry.label }}
          </div>
          <div class="mt-1 whitespace-pre-wrap break-words leading-6 text-zinc-700 dark:text-zinc-300">
            {{ entry.display }}
          </div>
        </div>
      </div>
    </div>

    <v-form
      v-else
      class="flex flex-col gap-4"
      @submit.prevent="handleAction('submit')"
    >
      <template v-for="field in fields" :key="field.name">
        <v-checkbox
          v-if="field.type === 'checkbox'"
          v-model="values[field.name]"
          :label="field.label || field.name"
          :hide-details="false"
          :aria-invalid="fieldInvalid(field)"
          density="comfortable"
          :disabled="submitted"
        />
        <v-radio-group
          v-else-if="field.type === 'radio'"
          v-model="values[field.name]"
          :label="field.label || field.name"
          :aria-invalid="fieldInvalid(field)"
          density="comfortable"
          :disabled="submitted"
        >
          <v-radio
            v-for="option in field.options || []"
            :key="String(option.value)"
            :label="option.label"
            :value="option.value"
          />
        </v-radio-group>
        <div
          v-else-if="field.type === 'select' || (kind === 'select' && field.options?.length)"
          class="space-y-1.5"
        >
          <label
            :for="`${block.id}-${field.name}`"
            class="block text-sm font-medium leading-5 text-zinc-800 dark:text-zinc-200"
          >
            {{ field.label || field.name }}
          </label>
          <v-select
            :id="`${block.id}-${field.name}`"
            v-model="values[field.name]"
            :items="field.options || []"
            item-title="label"
            item-value="value"
            :placeholder="field.placeholder"
            :required="field.required"
            :aria-label="field.label || field.name"
            :aria-invalid="fieldInvalid(field)"
            density="comfortable"
            variant="outlined"
            hide-details="auto"
            :disabled="submitted"
          />
        </div>
        <div v-else-if="field.type === 'textarea'" class="space-y-1.5">
          <label
            :for="`${block.id}-${field.name}`"
            class="block text-sm font-medium leading-5 text-zinc-800 dark:text-zinc-200"
          >
            {{ field.label || field.name }}
          </label>
          <v-textarea
            :id="`${block.id}-${field.name}`"
            v-model="values[field.name]"
            :placeholder="field.placeholder || answerPlaceholder"
            :required="field.required"
            :aria-label="field.label || field.name"
            :aria-invalid="fieldInvalid(field)"
            rows="3"
            density="comfortable"
            variant="outlined"
            hide-details="auto"
            class="interaction-field"
            :disabled="submitted"
          />
        </div>
        <v-file-input
          v-else-if="field.type === 'file' || kind === 'upload'"
          :label="field.label || field.name"
          :placeholder="field.placeholder"
          :required="field.required"
          :aria-invalid="fieldInvalid(field)"
          density="comfortable"
          variant="outlined"
          :disabled="submitted"
          show-size
          @update:model-value="(files) => onFileChange(field.name, files)"
        />
        <div v-else-if="field.type === 'date'" class="space-y-1.5">
          <label
            :for="`${block.id}-${field.name}`"
            class="block text-sm font-medium leading-5 text-zinc-800 dark:text-zinc-200"
          >
            {{ field.label || field.name }}
          </label>
          <v-text-field
            :id="`${block.id}-${field.name}`"
            v-model="values[field.name]"
            type="date"
            :required="field.required"
            :aria-label="field.label || field.name"
            :aria-invalid="fieldInvalid(field)"
            density="comfortable"
            variant="outlined"
            hide-details="auto"
            class="interaction-field"
            :disabled="submitted"
          />
        </div>
        <div v-else class="space-y-1.5">
          <label
            :for="`${block.id}-${field.name}`"
            class="block text-sm font-medium leading-5 text-zinc-800 dark:text-zinc-200"
          >
            {{ field.label || field.name }}
          </label>
          <v-text-field
            :id="`${block.id}-${field.name}`"
            v-model="values[field.name]"
            :type="field.type === 'number' ? 'number' : 'text'"
            :placeholder="field.placeholder || answerPlaceholder"
            :required="field.required"
            :aria-label="field.label || field.name"
            :aria-invalid="fieldInvalid(field)"
            density="comfortable"
            variant="plain"
            hide-details="auto"
            class="interaction-field"
            :disabled="submitted"
          />
        </div>
      </template>

      <div class="flex flex-wrap justify-end gap-2 pt-1">
        <v-btn
          v-for="action in actions"
          :key="action.id"
          :variant="action.primary ? 'flat' : 'tonal'"
          :disabled="action.primary && action.id !== 'cancel' && !isValid"
          :class="[
            'min-w-24 rounded-md text-none font-semibold shadow-none transition-colors [&_.v-btn__overlay]:!opacity-0',
            action.primary
              ? 'bg-[#1b5875]! text-white! hover:bg-[#164760]! disabled:bg-zinc-200! disabled:text-zinc-500! dark:bg-sky-400! dark:text-zinc-950! dark:hover:bg-sky-300! dark:disabled:bg-zinc-800! dark:disabled:text-zinc-500!'
              : 'text-zinc-700! dark:text-zinc-200!',
          ]"
          @click="handleAction(action.id)"
        >
          {{
            action.label ||
            (action.id === 'cancel' ? t('common.cancel') : t('interaction.submit'))
          }}
        </v-btn>
      </div>
    </v-form>
  </div>
</template>

<style scoped>
:deep(.interaction-field .v-field__input) {
  min-height: 2.5rem;
  padding-top: 0.45rem;
  padding-bottom: 0.45rem;
  font-size: 0.875rem;
  line-height: 1.35rem;
}

:deep(.interaction-field input::placeholder),
:deep(.interaction-field textarea::placeholder) {
  font-size: 0.875rem;
  color: rgb(113 113 122);
  opacity: 1;
}

:deep(.interaction-field .v-field) {
  border-radius: 0.5rem;
}

:deep(.interaction-field input.v-field__input:focus),
:deep(.interaction-field textarea.v-field__input:focus) {
  border-color: transparent !important;
  box-shadow: none !important;
  outline: none !important;
}

:global(.dark) :deep(.interaction-field .v-field) {
  background-color: rgb(24 24 27 / 0.55);
}

:global(.dark) :deep(.interaction-field .v-field__input) {
  color: rgb(244 244 245) !important;
  -webkit-text-fill-color: rgb(244 244 245);
}

:global(.dark) :deep(.interaction-field input.v-field__input),
:global(.dark) :deep(.interaction-field textarea.v-field__input) {
  color: rgb(244 244 245) !important;
  caret-color: rgb(125 211 252);
  -webkit-text-fill-color: rgb(244 244 245);
}

:global(.dark) :deep(.interaction-field input::placeholder),
:global(.dark) :deep(.interaction-field textarea::placeholder) {
  color: rgb(161 161 170);
}

:global(.dark) :deep(.interaction-field .v-field__outline) {
  color: rgb(63 63 70);
}

</style>
