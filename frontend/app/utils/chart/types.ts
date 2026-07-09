import type { ChartOutput } from '~/types/message';

export type EChartsOption = Record<string, unknown>;
export type ExtendedChartOutput = ChartOutput & Record<string, unknown>;
export type ExtendedChartSeries = ChartOutput['series'][number] & Record<string, unknown>;
