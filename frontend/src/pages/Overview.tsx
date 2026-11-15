import { lazy, Suspense } from 'react';
import { useApp } from '../AppContext';
import { Loading } from '../components/ui';

const MetricsOverview = lazy(() =>
  import('./MetricsOverview').then((page) => ({ default: page.MetricsOverview })),
);
const FullOverview = lazy(() =>
  import('./FullOverview').then((page) => ({ default: page.FullOverview })),
);

export function Overview() {
  const { isMetricsOnly } = useApp();
  const Screen = isMetricsOnly ? MetricsOverview : FullOverview;
  return (
    <Suspense fallback={<Loading />}>
      <Screen />
    </Suspense>
  );
}
