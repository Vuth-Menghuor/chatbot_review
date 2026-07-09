import { computed, ref, type MaybeRefOrGetter, toValue } from 'vue';
import type { MessageBlock } from '~/types/message';

export type ToolOutputView = 'json' | 'cards' | 'table';

function parsePayload(content: unknown): unknown {
  if (typeof content === 'string') {
    const trimmed = content.trim();
    if (!trimmed) return null;
    try {
      return JSON.parse(trimmed);
    } catch {
      return trimmed;
    }
  }
  if (content && typeof content === 'object') {
    const record = content as Record<string, unknown>;
    if (record.formattedOutput !== undefined) return record.formattedOutput;
    return content;
  }
  return content;
}

function inferDefaultView(
  payload: unknown,
  meta?: { view?: unknown; schema?: unknown },
): ToolOutputView {
  const metaView = meta?.view;
  if (metaView === 'cards' || metaView === 'table' || metaView === 'json') {
    return metaView;
  }
  const schema = meta?.schema;
  if (Array.isArray(payload) && payload.length > 0 && typeof payload[0] === 'object') {
    return 'table';
  }
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    return 'cards';
  }
  return 'json';
}

function schemaLabel(key: string, schema?: unknown): string {
  if (!schema || typeof schema !== 'object' || Array.isArray(schema)) return key;
  const props = (schema as Record<string, unknown>).properties;
  if (!props || typeof props !== 'object' || Array.isArray(props)) return key;
  const field = (props as Record<string, unknown>)[key];
  if (field && typeof field === 'object' && !Array.isArray(field)) {
    const title = (field as Record<string, unknown>).title;
    if (typeof title === 'string' && title.trim()) return title;
  }
  return key;
}

export function useToolOutputRenderer(blockSource: MaybeRefOrGetter<MessageBlock>) {
  const view = ref<ToolOutputView | null>(null);

  const block = computed(() => toValue(blockSource));
  const schema = computed(() => block.value.meta?.schema);
  const metaView = computed(() => block.value.meta?.view);
  const toolName = computed(() => {
    const metaName = block.value.meta?.toolName;
    if (typeof metaName === 'string' && metaName.trim()) return metaName;
    if (block.value.content && typeof block.value.content === 'object') {
      const name = (block.value.content as Record<string, unknown>).toolName;
      if (typeof name === 'string' && name.trim()) return name;
    }
    return '';
  });

  const payload = computed(() => parsePayload(block.value.content));
  const activeView = computed<ToolOutputView>(
    () =>
      view.value ??
      inferDefaultView(payload.value, { view: metaView.value, schema: schema.value }),
  );

  const cardEntries = computed(() => {
    const data = payload.value;
    if (!data || typeof data !== 'object' || Array.isArray(data)) return [];
    return Object.entries(data as Record<string, unknown>).map(([key, value]) => ({
      key,
      label: schemaLabel(key, schema.value),
      value: value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value),
    }));
  });

  const tableColumns = computed(() => {
    const rows = payload.value;
    if (!Array.isArray(rows) || !rows.length || typeof rows[0] !== 'object') return [];
    return Object.keys(rows[0] as Record<string, unknown>).map((key) => ({
      key,
      title: schemaLabel(key, schema.value),
    }));
  });

  const tableRows = computed(() => {
    const rows = payload.value;
    if (!Array.isArray(rows)) return [];
    return rows.map((row) => {
      if (!row || typeof row !== 'object') return {};
      const out: Record<string, string> = {};
      for (const [key, value] of Object.entries(row as Record<string, unknown>)) {
        out[key] = value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value);
      }
      return out;
    });
  });

  const jsonBlock = computed<MessageBlock>(() => ({
    ...block.value,
    type: 'code',
    meta: { ...block.value.meta, language: 'json' },
  }));

  const canShowCards = computed(() => cardEntries.value.length > 0);
  const canShowTable = computed(() => tableRows.value.length > 0 && tableColumns.value.length > 0);

  function setView(next: ToolOutputView) {
    view.value = next;
  }

  return {
    toolName,
    activeView,
    cardEntries,
    tableColumns,
    tableRows,
    jsonBlock,
    canShowCards,
    canShowTable,
    setView,
    isLoading: computed(() => block.value.isComplete === false),
  };
}
