import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export type Activity = { id: string; event: string; tenant?: string; status?: string; at: Date };
export function useLiveEvents() {
  const client = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [activity, setActivity] = useState<Activity[]>([]);
  useEffect(() => {
    const stream = new EventSource('/api/stream', { withCredentials: true });
    let timer: ReturnType<typeof setTimeout> | undefined;
    stream.addEventListener('stream.ready', () => {
      setConnected(true);
      void client.invalidateQueries({
        predicate: (q) => !['me', 'config'].includes(String(q.queryKey[0])),
      });
    });
    stream.onerror = () => {
      setConnected(false);
      void client.invalidateQueries({ queryKey: ['me'] });
    };
    const events = [
      'run.updated',
      'quality.updated',
      'alert.fired',
      'alert.resolved',
      'onboarding.step',
      'platform.changed',
      'access.changed',
      'metrics.refresh',
    ];
    const handle = (event: MessageEvent<string>) => {
      if (event.type === 'access.changed') {
        void client.invalidateQueries({ queryKey: ['me'] });
        void client.invalidateQueries({ queryKey: ['access'] });
        return;
      }
      if (event.type === 'metrics.refresh') {
        void client.invalidateQueries({
          predicate: (query) => !['me', 'config'].includes(String(query.queryKey[0])),
        });
        return;
      }
      const data = JSON.parse(event.data) as { tenant_id?: string; status?: string };
      setActivity((previous) =>
        [
          {
            id: crypto.randomUUID(),
            event: event.type,
            tenant: data.tenant_id,
            status: data.status,
            at: new Date(),
          },
          ...previous,
        ].slice(0, 12),
      );
      // Collapse a collector's batch into one cache refresh.
      if (timer) clearTimeout(timer);
      timer = setTimeout(
        () =>
          void client.invalidateQueries({
            predicate: (q) => !['me', 'config'].includes(String(q.queryKey[0])),
          }),
        250,
      );
    };
    events.forEach((event) => stream.addEventListener(event, handle as EventListener));
    return () => {
      stream.close();
      if (timer) clearTimeout(timer);
    };
  }, [client]);
  return { connected, activity };
}
