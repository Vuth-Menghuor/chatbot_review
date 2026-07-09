import * as echarts from 'echarts/core';
import {
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  RadarChart,
  HeatmapChart,
  TreemapChart,
  FunnelChart,
  GaugeChart,
  CandlestickChart,
  BoxplotChart,
  ParallelChart,
  SankeyChart,
  GraphChart,
  SunburstChart,
  MapChart,
  LinesChart,
  CustomChart,
} from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  DataZoomComponent,
  TimelineComponent,
  CalendarComponent,
  ToolboxComponent,
  MarkPointComponent,
  MarkLineComponent,
  MarkAreaComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

let registered = false;

/** Tree-shaken ECharts — call before init(). */
export function ensureEChartsRegistered() {
  if (registered) {
    return;
  }
  echarts.use([
    LineChart,
    BarChart,
    PieChart,
    ScatterChart,
    RadarChart,
    HeatmapChart,
    TreemapChart,
    FunnelChart,
    GaugeChart,
    CandlestickChart,
    BoxplotChart,
    ParallelChart,
    SankeyChart,
    GraphChart,
    SunburstChart,
    MapChart,
    LinesChart,
    CustomChart,
    TitleComponent,
    TooltipComponent,
    GridComponent,
    LegendComponent,
    VisualMapComponent,
    DataZoomComponent,
    TimelineComponent,
    CalendarComponent,
    ToolboxComponent,
    MarkPointComponent,
    MarkLineComponent,
    MarkAreaComponent,
    CanvasRenderer,
  ]);
  registered = true;
}

export { echarts };
