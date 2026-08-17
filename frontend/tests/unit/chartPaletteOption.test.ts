import test from 'node:test';
import assert from 'node:assert/strict';

import { buildBaseOption } from '../../app/utils/chart/base';
import { buildScatterOption } from '../../app/utils/chart/scatter';

test('single-series bar charts assign different colors per category', () => {
  const option = buildBaseOption({
    title: 'Trade Ranking',
    chartType: 'bar',
    xKey: 'label',
    data: [
      { label: 'China', value: 100 },
      { label: 'Thailand', value: 25 },
      { label: 'Indonesia', value: 15 },
    ],
    series: [{ key: 'value', name: 'Trade Value', type: 'bar' }],
  }, false);

  const series = Array.isArray(option.series) ? option.series[0] as Record<string, unknown> : {};
  const data = series.data as Array<Record<string, unknown>>;
  const colors = data.map((item) => (item.itemStyle as Record<string, unknown>).color);

  assert.equal(data.length, 3);
  assert.equal(new Set(colors).size, 3);
});

test('multi-series charts assign fallback colors by series', () => {
  const option = buildScatterOption({
    title: 'Trade Scatter',
    chartType: 'scatter',
    xKey: 'x',
    data: [{ x: 1, imports: 100, exports: 80 }],
    series: [
      { key: 'imports', name: 'Imports', type: 'scatter' },
      { key: 'exports', name: 'Exports', type: 'scatter' },
    ],
  }, false);

  const series = option.series as Array<Record<string, unknown>>;
  const colors = series.map((item) => (item.itemStyle as Record<string, unknown>).color);

  assert.equal(series.length, 2);
  assert.equal(new Set(colors).size, 2);
});
