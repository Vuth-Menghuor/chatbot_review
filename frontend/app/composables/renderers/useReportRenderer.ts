import { computed } from 'vue';
import type { MessageBlock, ReportTask } from '~/types/message';

type UiReportStatus = 'pending' | 'processing' | 'completed' | 'error';

function normalizeStatus(status?: ReportTask['status']): UiReportStatus {
  if (status === 'success') return 'completed';
  if (status === 'failed') return 'error';
  if (status === 'processing' || status === 'completed' || status === 'error') return status;
  return 'pending';
}

/**
 * Report card — mirrors API `content` and `status` only (no timed fake completion).
 */
export function useReportRenderer(props: {
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}) {
  const data = computed<ReportTask>(() => (props.block.content || {}) as ReportTask);

  const shownStatus = computed<UiReportStatus>(() => {
    if (props.block.isComplete === false) return 'processing';
    return normalizeStatus(data.value?.status);
  });

  const handleDownload = () => {
    if (data.value?.reportUrl) window.open(data.value.reportUrl, '_blank');
  };

  return {
    data,
    shownStatus,
    handleDownload,
  };
}
