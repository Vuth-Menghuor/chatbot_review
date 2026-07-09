import { computed, reactive, ref, watch, type MaybeRefOrGetter, toValue } from 'vue';
import type { InteractionField, MessageBlock } from '~/types/message';

type InteractionContent = Record<string, unknown>;

function asInteractionContent(content: unknown): InteractionContent {
  return content && typeof content === 'object' && !Array.isArray(content)
    ? (content as InteractionContent)
    : {};
}

function fieldDefault(field: InteractionField): unknown {
  if (field.default !== undefined) return field.default;
  if (field.type === 'checkbox') return false;
  if (field.type === 'file') return null;
  return '';
}

function isFieldFilled(field: InteractionField, value: unknown): boolean {
  if (field.type === 'checkbox') return value === true;
  if (field.type === 'file') return value instanceof File || (typeof value === 'string' && value.trim().length > 0);
  if (value === null || value === undefined) return false;
  return String(value).trim().length > 0;
}

export function useInteractionRenderer(blockSource: MaybeRefOrGetter<MessageBlock>) {
  const block = computed(() => toValue(blockSource));
  const data = computed(() => asInteractionContent(block.value.content));

  const fields = computed(() =>
    Array.isArray(data.value.fields) ? (data.value.fields as InteractionField[]) : [],
  );

  const kind = computed(() => String(data.value.kind || 'form').toLowerCase());
  const values = reactive<Record<string, unknown>>({});
  const submitted = ref(false);
  const submittedAction = ref<string | null>(null);
  const submittedValues = ref<Record<string, unknown>>({});

  watch(
    fields,
    (nextFields) => {
      for (const field of nextFields) {
        if (!(field.name in values)) {
          values[field.name] = fieldDefault(field);
        }
      }
    },
    { immediate: true },
  );

  watch(
    data,
    (next) => {
      if (next.submitted === true) {
        submitted.value = true;
        submittedAction.value =
          typeof next.submittedAction === 'string' ? next.submittedAction : 'submit';
        submittedValues.value =
          next.submittedValues && typeof next.submittedValues === 'object'
            ? (next.submittedValues as Record<string, unknown>)
            : {};
      }
    },
    { immediate: true },
  );

  const isValid = computed(() =>
    fields.value.every((field) => !field.required || isFieldFilled(field, values[field.name])),
  );

  const summaryEntries = computed(() =>
    Object.entries(submittedValues.value).map(([key, value]) => {
      const field = fields.value.find((f) => f.name === key);
      const label = field?.label || key;
      let display = '—';
      if (value instanceof File) display = value.name;
      else if (typeof value === 'boolean') display = value ? 'Yes' : 'No';
      else if (value != null) display = String(value);
      return { key, label, display };
    }),
  );

  function buildPayload(action: string) {
    const serialized: Record<string, unknown> = {};
    for (const field of fields.value) {
      const value = values[field.name];
      if (value instanceof File) {
        serialized[field.name] = { name: value.name, size: value.size, type: value.type };
      } else {
        serialized[field.name] = value;
      }
    }
    return serialized;
  }

  function markSubmitted(action: string, payload: Record<string, unknown>) {
    submitted.value = true;
    submittedAction.value = action;
    submittedValues.value = { ...payload };
  }

  return {
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
  };
}
