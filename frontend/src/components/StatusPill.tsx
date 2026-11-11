function statusTone(status: string): 'ok' | 'warn' | 'bad' | 'run' | 'idle' {
  if (['healthy', 'success', 'pass', 'enabled', 'up', 'resolved'].includes(status)) return 'ok';
  if (['degraded', 'warning', 'acked', 'medium'].includes(status)) return 'warn';
  if (['down', 'failed', 'fail', 'error', 'critical', 'high', 'firing'].includes(status))
    return 'bad';
  if (['running', 'started', 'queued'].includes(status)) return 'run';
  return 'idle';
}

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
      data-tone={statusTone(status)}
    >
      {dot && <span className="status-dot" style={{ background: 'currentColor' }} />}
      {status === 'acked' ? 'acknowledged' : status.replaceAll('_', ' ')}
    </span>
  );
}
