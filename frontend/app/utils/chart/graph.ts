import type { EChartsOption, ExtendedChartOutput } from './types';

export function buildGraphOption(out: ExtendedChartOutput, isDark: boolean): EChartsOption {
  const textColor = isDark ? '#e4e4e7' : '#27272a';
  const gridLineColor = isDark ? '#27272a' : '#e4e4e7';

  return {
    title: {
      text: out.title || '',
      left: 'center',
      top: '4%',
      textStyle: { color: textColor, fontSize: 16, fontWeight: 'bold' },
    },
    tooltip: {
      backgroundColor: isDark ? '#18181b' : '#ffffff',
      borderColor: gridLineColor,
      textStyle: { color: textColor },
    },
    series: [
      {
        type: 'graph',
        layout: 'force',
        symbolSize: 30,
        roam: true,
        label: { show: true, color: textColor },
        force: { repulsion: 100 },
        data: out.nodes || out.data || [],
        links: out.links || out.edges || [],
        lineStyle: { opacity: 0.9, width: 2, curveness: 0 },
      },
    ],
  };
}
