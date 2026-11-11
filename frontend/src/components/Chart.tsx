import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import type { EChartsCoreOption } from 'echarts/core';

const EChart = lazy(() => import('./EChart').then((module) => ({ default: module.EChart })));

export function Chart({
  option,
  height = 240,
  label,
}: {
  option: EChartsCoreOption;
  height?: number;
  label: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [nearViewport, setNearViewport] = useState(false);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    if (typeof IntersectionObserver === 'undefined') {
      setNearViewport(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setNearViewport(true);
          observer.disconnect();
        }
      },
      { rootMargin: '180px 0px' },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={host}
      className="chart-deferred"
      style={{ height, width: '100%' }}
      role="img"
      aria-label={label}
    >
      {nearViewport && (
        <Suspense fallback={<div className="chart-loading-placeholder" aria-hidden="true" />}>
          <EChart option={option} height={height} />
        </Suspense>
      )}
    </div>
  );
}
