import { computed } from 'vue';
import type { MessageBlock, TableData } from '~/types/message';
import { useAnimStaggerReveal } from '../common/useAnimStaggerReveal';
import { useRenderAnimation } from '../common/useRenderAnimation';

function isTableData(content: unknown): content is TableData {
  if (!content || typeof content !== 'object') return false;
  const value = content as Partial<TableData>;
  return Array.isArray(value.columns) && Array.isArray(value.rows);
}

/**
 * useTableRenderer
 * Provides table data parsing and row reveal state for TableRenderer.
 */
export function useTableRenderer(props: {
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}) {
  const anim = useRenderAnimation();
  const data = computed<TableData>(() => {
    const content = props.block.content;
    if (isTableData(content)) return content;
    return { columns: [], rows: [] };
  });

  const columns = computed(() => data.value.columns ?? []);
  const rows = computed(() => data.value.rows ?? []);

  /** SSE / LM Studio: fence closed but table JSON still filling in. */
  const isStreamingLayout = computed(
    () => props.block.isComplete === false && rows.value.length === 0,
  );

  const { visibleItems: visibleRows } = useAnimStaggerReveal({
    items: rows,
    enabled: computed(() => Boolean(props.animate)),
    animId: computed(() => props.animId ?? props.block.id),
    intervalMs: anim.tableRowMs,
    initialVisible: 1,
    maxVisible: anim.maxStaggerItems,
  });

  return {
    columns,
    visibleRows,
    isStreamingLayout,
  };
}
