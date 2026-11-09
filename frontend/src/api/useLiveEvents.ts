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
      void client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' });
    });
    stream.onerror = () => setConnected(false);
    const events = [
      'run.updated',
      'alert.fired',
      'alert.resolved',
      'onboarding.step',
      'platform.changed',
    ];
    const handle = (event: MessageEvent<string>) => {
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
        () => void client.invalidateQueries({ predicate: (q) => q.queryKey[0] !== 'me' }),
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
