import { STATUS_COLORS } from './statusColors';
export function StatusPill({ status, dot = true }: { status: string; dot?: boolean }) {
  return (
    <span
      className="status-pill"
      style={{
        color: STATUS_COLORS[status] || '#83909e',
        background: `${STATUS_COLORS[status] || '#83909e'}13`,
      }}
    >
      {dot && <span className="status-dot" style={{ background: 'currentColor' }} />}
      {status.replaceAll('_', ' ')}
    </span>
  );
}
