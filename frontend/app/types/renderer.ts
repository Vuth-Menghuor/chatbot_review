import type { Ref } from 'vue';
import type { MessageBlock } from './message';

export interface TableColumn {
  key: string;
  title: string;
}

export interface TableData {
  columns: TableColumn[];
  rows: Record<string, unknown>[];
}

export type ChartKind =
  | 'line'
  | 'bar'
  | 'horizontal-bar'
  | 'horizontalbar'
  | 'area'
  | 'pie'
  | 'donut'
  | 'scatter'
  | 'radar'
  | 'heatmap'
  | 'treemap'
  | 'tree-map'
  | 'funnel'
  | 'gauge'
  | 'candlestick'
  | 'sankey'
  | 'graph'
  | 'sunburst';

export interface ChartSeries {
  key: string;
  name: string;
  color: string;
  type?: ChartKind | 'line' | 'bar' | 'scatter';
  stack?: string;
  areaStyle?: Record<string, unknown>;
  markPoint?: Record<string, unknown>;
  markLine?: Record<string, unknown>;
}

export interface BulletLegendItem {
  name: string;
  color: string;
}

export interface ChartOutput {
  title?: string;
  chartType?: ChartKind;
  xKey: string;
  xLabel?: string;
  yLabel?: string;
  data: Array<Record<string, string | number>>;
  series: ChartSeries[];
  horizontal?: boolean;
  stacked?: boolean;
  dataZoom?: boolean;
  markPoint?: boolean | Record<string, unknown>;
  markLine?: boolean | Record<string, unknown>;
  xCategories?: string[];
  yCategories?: string[];
  nodes?: Array<Record<string, unknown>>;
  links?: Array<Record<string, unknown>>;
}

export interface ChartUIToolInvocation {
  state: 'input-available' | 'input-streaming' | 'output-available' | 'output-error' | string;
  output?: ChartOutput;
}

export interface LegacyChartTask {
  title?: string;
  status?: 'pending' | 'processing' | 'completed' | 'error';
  type?: 'chart' | 'line' | 'bar' | 'area' | 'pie' | 'doughnut' | 'donut';
  mode?: 'sync' | 'async' | string;
  toolName?: string;
  taskId?: string;
  prompt?: string;
  chartType?: ChartKind;
  output?: ChartOutput;
}

export interface WorkflowStep {
  label: string;
  status: 'complete' | 'active' | 'pending' | 'error';
  details?: string;
  timestamp?: string;
}

export interface WorkflowData {
  title?: string;
  steps: WorkflowStep[];
}

export interface OCRData {
  title?: string;
  text: string;
  language?: string;
  confidence?: number;
  pages?: number;
  fields?: Record<string, string>;
}

export interface PredictionTaxRate {
  label: string;
  value: string;
}

export interface PredictionMetric {
  label: string;
  value: string | number;
}

export interface Prediction {
  toolName?: string;
  title?: string;
  label?: string;
  hsCode?: string;
  productName?: string;
  category?: string;
  predictedVolume?: number;
  year?: number;
  value?: string | number;
  unit?: string;
  metrics?: PredictionMetric[];
  reason?: string;
  evidence?: string[];
  sourceName?: string;
  sourceUrl?: string;
  preliminary?: boolean;
  tariffSectionTitle?: string;
  taxRates?: PredictionTaxRate[];
  importDuty?: string;
  specialTax?: string;
  vat?: string;
  exportTax?: string;
  alternatives?: Array<{
    hsCode: string;
    productName: string;
    category?: string;
    reason?: string;
    importDuty?: string;
    specialTax?: string;
    vat?: string;
    exportTax?: string;
  }>;
}

export interface ReportTask {
  title?: string;
  toolName?: string;
  type?: 'report' | string;
  mode?: 'sync' | 'async' | string;
  taskId?: string;
  status?: 'pending' | 'processing' | 'completed' | 'error' | 'success' | 'failed';
  error?: string;
  reportUrl?: string;
  fileSize?: string;
  format?: string;
  error?: string;
}

export interface RenderAnimationConfig {
  enabled: boolean;
  thinkingMs: number;
  markdownChunkMs: number;
  blockEnterMs: number;
  tableRowMs: number;
  workflowStepMs: number;
  stepsStepMs: number;
  ocrFieldMs: number;
  predictionCountUpMs: number;
  reportStatusMs: number;
  jsonCharChunk: number;
  jsonTickMs: number;
  maxStaggerItems: number;
}

export interface UseAnimStaggerRevealOptions<T> {
  items: Ref<T[]>;
  enabled: Ref<boolean>;
  animId: Ref<string | undefined>;
  intervalMs: number;
  initialVisible?: number;
  maxVisible?: number;
}

export interface UseStepsRendererProps {
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}

export interface UseWorkflowRendererProps {
  block: MessageBlock;
  animate?: boolean;
  animId?: string;
}
