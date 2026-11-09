import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart, HeatmapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  MarkLineComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { EChartsCoreOption } from 'echarts/core';

echarts.use([
  BarChart,
  LineChart,
  HeatmapChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  VisualMapComponent,
  MarkLineComponent,
  CanvasRenderer,
]);
export function Chart({
  option,
  height = 240,
  label,
}: {
  option: EChartsCoreOption;
  height?: number;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const instance = echarts.init(ref.current);
    instance.setOption({
      textStyle: { fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11, color: '#81909f' },
      grid: { left: 46, right: 24, top: 30, bottom: 36, containLabel: true },
      tooltip: { trigger: 'axis', confine: true },
      ...option,
    });
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
      instance.dispose();
    };
  }, [option]);
  return <div ref={ref} style={{ height, width: '100%' }} role="img" aria-label={label} />;
}
