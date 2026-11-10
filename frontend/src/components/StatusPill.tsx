import { STATUS_COLORS } from './statusColors';
export function StatusPill({
  status,
  dot = true,
  tip,
}: {
  status: string;
  dot?: boolean;
  tip?: string;
}) {
  return (
    <span
      data-tip={tip}
      className={`status-pill${tip ? ' has-tip tip-below' : ''}`}
      style={{
        color: STATUS_COLORS[status] || '#83909e',
        background: `${STATUS_COLORS[status] || '#83909e'}13`,
      }}
    >
      {dot && <span className="status-dot" style={{ background: 'currentColor' }} />}
      {status === 'acked' ? 'acknowledged' : status.replaceAll('_', ' ')}
    </span>
  );
}
