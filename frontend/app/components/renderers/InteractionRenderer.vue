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
    class="my-4 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    :aria-busy="!submitted && block.isComplete === false"
  >
    <div class="mb-4">
      <h3 class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">
        {{ data.title || t('interaction.title') }}
      </h3>
      <p v-if="data.description" class="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
        {{ data.description }}
      </p>
    </div>

    <div
      v-if="submitted"
      class="flex flex-col gap-3"
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
      <div v-if="summaryEntries.length" class="flex flex-wrap gap-2">
        <v-chip
          v-for="entry in summaryEntries"
          :key="entry.key"
          size="small"
          variant="tonal"
          class="text-xs"
        >
          <span class="font-semibold">{{ entry.label }}:</span>
          <span class="ml-1">{{ entry.display }}</span>
        </v-chip>
      </div>
    </div>

    <v-form
      v-else
      class="flex flex-col gap-3"
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
        <v-select
          v-else-if="field.type === 'select' || (kind === 'select' && field.options?.length)"
          v-model="values[field.name]"
          :items="field.options || []"
          item-title="label"
          item-value="value"
          :label="field.label || field.name"
          :placeholder="field.placeholder"
          :required="field.required"
          :aria-invalid="fieldInvalid(field)"
          density="comfortable"
          variant="outlined"
          :disabled="submitted"
        />
        <v-textarea
          v-else-if="field.type === 'textarea'"
          v-model="values[field.name]"
          :label="field.label || field.name"
          :placeholder="field.placeholder"
          :required="field.required"
          :aria-invalid="fieldInvalid(field)"
          rows="3"
          density="comfortable"
          variant="outlined"
          :disabled="submitted"
        />
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
        <v-text-field
          v-else-if="field.type === 'date'"
          v-model="values[field.name]"
          type="date"
          :label="field.label || field.name"
          :required="field.required"
          :aria-invalid="fieldInvalid(field)"
          density="comfortable"
          variant="outlined"
          :disabled="submitted"
        />
        <v-text-field
          v-else
          v-model="values[field.name]"
          :type="field.type === 'number' ? 'number' : 'text'"
          :label="field.label || field.name"
          :placeholder="field.placeholder"
          :required="field.required"
          :aria-invalid="fieldInvalid(field)"
          density="comfortable"
          variant="outlined"
          :disabled="submitted"
        />
      </template>

      <div class="mt-1 flex flex-wrap gap-2">
        <v-btn
          v-for="action in actions"
          :key="action.id"
          :color="action.primary ? 'primary' : undefined"
          :variant="action.primary ? 'flat' : 'tonal'"
          :disabled="action.primary && action.id !== 'cancel' && !isValid"
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
