import test from 'node:test';
import assert from 'node:assert/strict';

import { buildEchartsOptionFromOutput } from '../../app/utils/chart';
import { buildPieOption } from '../../app/utils/chart/pie';

test('pie chart assigns different colors per data slice and shows labels', () => {
  const option = buildPieOption({
    title: 'Trade Volume Ranking',
    chartType: 'pie',
    xKey: 'label',
    data: [
      { label: 'China', value: 100 },
      { label: 'Thailand', value: 25 },
      { label: 'Indonesia', value: 15 },
      { label: 'Singapore', value: 10 },
      { label: 'Malaysia', value: 8 },
    ],
    series: [{ key: 'value', name: 'Trade Value', type: 'pie', color: '#2563eb' }],
  }, false);

  const colors = option.color;
  assert.ok(Array.isArray(colors));
  assert.equal(colors.length, 5);
  assert.ok(new Set(colors).size > 1);

  const series = Array.isArray(option.series) ? option.series[0] as Record<string, unknown> : {};
  const label = series.label as Record<string, unknown>;
  assert.equal(label.show, true);
  assert.equal(label.position, 'outside');
  assert.equal(label.formatter, '{b}\n{d}%');
});

test('chart-level pie type renders as pie even when upstream series says bar', () => {
  const option = buildEchartsOptionFromOutput({
    title: 'Trade Volume Ranking',
    chartType: 'pie',
    xKey: 'label',
    data: [
      { label: 'China', trade_value_usd: 9834780841.9 },
      { label: 'Thailand', trade_value_usd: 1165960835.69 },
    ],
    series: [{ key: 'trade_value_usd', name: 'Trade Value (USD)', type: 'bar' }],
  }, false);

  const series = Array.isArray(option.series) ? option.series[0] as Record<string, unknown> : {};

  assert.equal(series.type, 'pie');
});
