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
import type { EChartsCoreOption, EChartsType } from 'echarts/core';

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
  const chart = useRef<EChartsType | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    const instance = echarts.init(ref.current);
    chart.current = instance;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => instance.resize());
    });
    observer.observe(ref.current);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, []);
  useEffect(() => {
    const pageTooltip =
      option && typeof option === 'object' && 'tooltip' in option
        ? (option.tooltip as Record<string, unknown>)
        : {};
    chart.current?.setOption(
      {
        animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
        animationDuration: 240,
        animationDurationUpdate: 260,
        textStyle: { fontFamily: 'Inter, system-ui, sans-serif', fontSize: 11, color: '#81909f' },
        grid: { left: 46, right: 24, top: 30, bottom: 36, containLabel: true },
        ...option,
        tooltip: {
          trigger: 'axis',
          ...pageTooltip,
          confine: true,
          backgroundColor: 'rgba(13, 24, 36, 0.96)',
          borderWidth: 0,
          textStyle: { color: '#e8eff6', fontSize: 12 },
          extraCssText:
            'border-radius: 10px; box-shadow: 0 14px 34px rgba(5, 12, 22, 0.35); padding: 10px 12px;',
        },
      },
      { replaceMerge: ['series'], lazyUpdate: true },
    );
  }, [option]);
  return <div ref={ref} style={{ height, width: '100%' }} role="img" aria-label={label} />;
}
