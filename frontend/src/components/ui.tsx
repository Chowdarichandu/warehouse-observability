import type { ReactNode } from 'react';
import { AlertCircle, ArrowLeft, ArrowRight, Database, Inbox } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';

export function PageHeader({
  title,
  description,
  eyebrow = 'WORKSPACE',
  actions,
}: {
  title: string;
  description: string;
  eyebrow?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-actions">{actions}</div>
    </div>
  );
}
export function Panel({
  title,
  subtitle,
  children,
  action,
  className = '',
}: {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      {title && (
        <div className="panel-heading">
          <div>
            <h2>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}
export function Loading() {
  return (
    <div role="status" aria-label="Loading" className="loading-grid">
      {[0, 1, 2, 3].map((n) => (
        <div key={n} className="skeleton" />
      ))}
    </div>
  );
}
export function Empty({
  title = 'No results in this view',
  children = 'Try a wider time range or clear the filters.',
}: {
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <Inbox size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="notice danger" role="alert">
      <AlertCircle size={18} />
      <div>
        <strong>Unable to load this view</strong>
        <p>{error.message}</p>
        <button onClick={() => window.location.reload()}>Try again</button>
      </div>
    </div>
  );
}
export function Pagination({
  total,
  page,
  size = 25,
  onChange,
}: {
  total: number;
  page: number;
  size?: number;
  onChange: (page: number) => void;
}) {
  if (!total) return null;
  return (
    <div className="pagination">
      <span>
        Showing {Math.min((page - 1) * size + 1, total)}–{Math.min(page * size, total)} of{' '}
        {total.toLocaleString()}
      </span>
      <div>
        <button aria-label="Previous page" disabled={page === 1} onClick={() => onChange(page - 1)}>
          <ArrowLeft size={14} />
        </button>
        <span>
          Page {page} of {Math.max(1, Math.ceil(total / size))}
        </span>
        <button
          aria-label="Next page"
          disabled={page * size >= total}
          onClick={() => onChange(page + 1)}
        >
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
export function useFilters() {
  const [params, setParams] = useSearchParams();
  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next);
  }
  const range = params.get('range') || '24h';
  return {
    params,
    set,
    range,
    rangeQuery:
      range === 'custom' && params.get('from') && params.get('to')
        ? `from=${encodeURIComponent(params.get('from') || '')}&to=${encodeURIComponent(params.get('to') || '')}`
        : `range=${range === 'custom' ? '24h' : range}`,
    page: Number(params.get('page') || 1),
  };
}
export function Time({ value, relative = false }: { value?: string | null; relative?: boolean }) {
  if (!value) return <span className="muted">—</span>;
  const date = new Date(value);
  const minutes = Math.max(0, Math.floor((Date.now() - date.getTime()) / 60000));
  return (
    <time dateTime={value} title={date.toISOString()}>
      {relative
        ? minutes < 1
          ? 'Just now'
          : minutes < 60
            ? `${minutes}m ago`
            : minutes < 1440
              ? `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`
              : `${Math.floor(minutes / 1440)}d ago`
        : date.toLocaleString([], {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          })}
    </time>
  );
}
export function NumberValue({ value, suffix = '' }: { value?: number | null; suffix?: string }) {
  return (
    <>
      {value == null ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
      {value != null && suffix}
    </>
  );
}
export function Source({ source }: { source: string }) {
  return (
    <span className={`source source-${source}`}>
      <Database size={13} />
      {source === 'mysql' ? 'MySQL' : 'MongoDB'}
    </span>
  );
}
export function TenantLink({ id }: { id: string }) {
  return (
    <Link className="text-link" to={`/tenants/${id}`}>
      {id.replaceAll('_', ' ')}
    </Link>
  );
}
export function Back({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link className="back-link" to={to}>
      <ArrowLeft size={14} />
      {children}
    </Link>
  );
}
export function formatDuration(seconds?: number | null) {
  return seconds == null ? '—' : seconds < 60 ? `${seconds}s` : `${(seconds / 60).toFixed(1)}m`;
}
