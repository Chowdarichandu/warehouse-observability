import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { Bookmark, GitCompareArrows, Trash2 } from 'lucide-react';
import { api, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { StatusPill } from './StatusPill';
import {
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Panel,
  TenantLink,
  Time,
  formatDuration,
  useFilters,
} from './ui';

const SAVED_FILTERS = [
  'tenant',
  'status',
  'source',
  'load',
  'stage',
  'error_class',
  'q',
  'sort',
  'range',
  'from',
  'to',
];

export function SavedRunViews() {
  const [params, setParams] = useSearchParams();
  const [name, setName] = useState('');
  const [selected, setSelected] = useState('');
  const { notify } = useApp();
  const client = useQueryClient();
  const views = useQuery({
    queryKey: ['saved-views'],
    queryFn: () => api<Schema<'SavedViews'>>('/saved-views'),
  });
  const save = useMutation({
    mutationFn: () =>
      api<Schema<'SavedView'>>('/saved-views', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          filters: Object.fromEntries(
            SAVED_FILTERS.filter((k) => params.has(k)).map((k) => [k, params.get(k)]),
          ),
        }),
      }),
    onSuccess: () => {
      setName('');
      notify('View saved to your account.');
      void client.invalidateQueries({ queryKey: ['saved-views'] });
    },
    onError: (error) => notify(error.message),
  });
  const remove = useMutation({
    mutationFn: () => api<Schema<'Message'>>(`/saved-views/${selected}`, { method: 'DELETE' }),
    onSuccess: () => {
      setSelected('');
      notify('Saved view removed.');
      void client.invalidateQueries({ queryKey: ['saved-views'] });
    },
    onError: (error) => notify(error.message),
  });
  return (
    <div className="saved-views">
      <div className="inline-flex">
        <Bookmark size={15} />
        <strong>Your views</strong>
        <select
          aria-label="Saved investigation views"
          value={selected}
          disabled={views.isPending || !!views.error}
          onChange={(e) => {
            setSelected(e.target.value);
            const view = views.data?.items.find((v) => String(v.id) === e.target.value);
            if (view) setParams(new URLSearchParams(view.filters));
          }}
        >
          <option value="">{views.isPending ? 'Loading views…' : 'Choose a saved view'}</option>
          {views.data?.items.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </select>
        <button
          className="icon-button"
          aria-label="Delete selected view"
          disabled={!selected || remove.isPending}
          onClick={() => remove.mutate()}
        >
          <Trash2 size={14} />
        </button>
      </div>
      <form
        className="inline-flex"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <input
          aria-label="New saved view name"
          placeholder="Name these filters…"
          maxLength={80}
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <button
          className="button small"
          disabled={!name.trim() || save.isPending || (views.data?.items.length || 0) >= 30}
        >
          <Bookmark size={13} />
          Save view
        </button>
      </form>
      <span className="muted">
        {views.error
          ? views.error.message
          : 'Save your current filters and time range to reopen this investigation later. Private to your account.'}
      </span>
    </div>
  );
}

export function RunComparison({
  current,
  previous,
}: {
  current: Schema<'RunDetail'>;
  previous: Schema<'Run'>[];
}) {
  const { params, set } = useFilters();
  const key = params.get('compare') || '';
  const other = useQuery({
    queryKey: ['comparison', key],
    queryFn: () => api<Schema<'RunDetail'>>(runPath(key)),
    enabled: !!key,
  });
  const a = current.run;
  const b = other.data?.run;
  const metrics: {
    label: string;
    current: number | null | undefined;
    previous: number | null | undefined;
    duration?: boolean;
  }[] = [
    { label: 'Duration', current: a.duration_s, previous: b?.duration_s, duration: true },
    { label: 'Queue delay', current: a.queue_delay_s, previous: b?.queue_delay_s, duration: true },
    { label: 'Rows synced', current: a.rows_synced, previous: b?.rows_synced },
    { label: 'Bytes synced', current: a.bytes_synced, previous: b?.bytes_synced },
    { label: 'Airbyte attempts', current: a.airbyte_attempts, previous: b?.airbyte_attempts },
  ];
  const streamNames = [
    ...new Set([...current.streams, ...(other.data?.streams || [])].map((s) => s.stream_name)),
  ].sort();
  return (
    <Panel
      title="Compare runs"
      subtitle="Compare recorded metrics with another attempt of this pipeline."
      action={<GitCompareArrows size={17} />}
    >
      <div className="filter-bar">
        <label className="comparison-picker">
          Baseline run
          <select
            aria-label="Comparison baseline"
            value={key}
            onChange={(e) => set('compare', e.target.value)}
          >
            <option value="">Choose a previous run</option>
            {previous.map((r) => (
              <option key={r.run_key} value={r.run_key}>
                {new Date(r.started_at || r.collected_at).toLocaleString()} · {r.status}
              </option>
            ))}
            {key && !previous.some((r) => r.run_key === key) && (
              <option value={key}>Linked baseline</option>
            )}
          </select>
        </label>
        {b && (
          <Link className="text-link" to={runPath(b.run_key)}>
            Open baseline run
          </Link>
        )}
      </div>
      {!key ? (
        <Empty title="Choose a baseline">
          Duration, row counts, attempts, and per-stream changes appear side by side.
        </Empty>
      ) : other.isPending ? (
        <Loading />
      ) : other.error ? (
        <ErrorState error={other.error} />
      ) : (
        b && (
          <>
            {(a.tenant_id !== b.tenant_id ||
              a.source_type !== b.source_type ||
              a.load_type !== b.load_type) && (
              <div className="notice info">
                These runs belong to different pipelines. Differences may not be comparable.
              </div>
            )}
            <div className="table-scroll">
              <table aria-label="Run comparison">
                <thead>
                  <tr>
                    <th>Metric</th>
                    <th>Current run</th>
                    <th>Baseline</th>
                    <th>Change</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th>Status</th>
                    <td>
                      <StatusPill status={a.status} />
                    </td>
                    <td>
                      <StatusPill status={b.status} />
                    </td>
                    <td>—</td>
                  </tr>
                  {metrics.map((m) => (
                    <tr key={m.label}>
                      <th>{m.label}</th>
                      <td>
                        {m.duration ? formatDuration(m.current) : <NumberValue value={m.current} />}
                      </td>
                      <td>
                        {m.duration ? (
                          formatDuration(m.previous)
                        ) : (
                          <NumberValue value={m.previous} />
                        )}
                      </td>
                      <td className="mono">
                        {m.current == null || m.previous == null
                          ? '—'
                          : `${m.current - m.previous > 0 ? '+' : ''}${(m.current - m.previous).toLocaleString()}${m.duration ? 's' : ''}`}
                      </td>
                    </tr>
                  ))}
                  <tr>
                    <th>Error class</th>
                    <td>{current.error?.error_class || '—'}</td>
                    <td>{other.data?.error?.error_class || '—'}</td>
                    <td>—</td>
                  </tr>
                  {streamNames.map((name) => {
                    const left = current.streams.find((s) => s.stream_name === name)?.records;
                    const right = other.data?.streams.find((s) => s.stream_name === name)?.records;
                    return (
                      <tr key={name}>
                        <th>Stream · {name}</th>
                        <td>
                          <NumberValue value={left} />
                        </td>
                        <td>
                          <NumberValue value={right} />
                        </td>
                        <td>
                          {left == null || right == null ? (
                            '—'
                          ) : (
                            <NumberValue value={left - right} />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="panel-footer">
              Change = current − baseline. Missing metrics remain unknown.
            </div>
          </>
        )
      )}
    </Panel>
  );
}

export function EventTimeline({
  runKey = '',
  tenant = '',
  rangeQuery = 'range=24h',
}: {
  runKey?: string;
  tenant?: string;
  rangeQuery?: string;
}) {
  const query = useQuery({
    queryKey: ['investigation-timeline', runKey, tenant, rangeQuery],
    queryFn: () =>
      api<Schema<'InvestigationTimeline'>>(
        `/investigation/timeline?${rangeQuery}&tenant=${encodeURIComponent(tenant)}&run_key=${encodeURIComponent(runKey)}`,
      ),
  });
  return (
    <Panel
      title="Event timeline"
      subtitle="Pipeline activity and tenant context in one chronological view."
    >
      {query.isPending ? (
        <Loading />
      ) : query.error ? (
        <ErrorState error={query.error} />
      ) : !query.data.items.length ? (
        <Empty title="No events in this time range" />
      ) : (
        <>
          <ol className="investigation-timeline">
            {query.data.items.map((event) => (
              <li key={event.id}>
                <div className="event-marker" aria-hidden="true" />
                <div className="event-time">
                  <Time value={event.at} />
                  <span className="tag">{event.kind}</span>
                </div>
                <div className="event-content">
                  <strong>{event.title}</strong>
                  <div className="inline-flex">
                    <StatusPill status={event.status} />
                    {event.tenant_id && <TenantLink id={event.tenant_id} />}{' '}
                    {event.run_key && (
                      <Link className="text-link" to={runPath(event.run_key)}>
                        View run
                      </Link>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ol>
          <div className="panel-footer">
            {query.data.truncated
              ? 'Showing the newest 200 events. Narrow your filters to see more. '
              : ''}
            {query.data.note}
          </div>
        </>
      )}
    </Panel>
  );
}

export function Activity({ embedded = false }: { embedded?: boolean }) {
  const { params, set, rangeQuery } = useFilters();
  return (
    <>
      {!embedded && (
        <PageHeader
          title="Activity"
          description="Follow runs, alerts, onboarding, and operator actions across your workspace."
        />
      )}
      <div className="filter-bar">
        <input
          aria-label="Activity tenant filter"
          placeholder="Filter by tenant slug"
          value={params.get('tenant') || ''}
          onChange={(e) => set('tenant', e.target.value)}
        />
      </div>
      <EventTimeline tenant={params.get('tenant') || ''} rangeQuery={rangeQuery} />
    </>
  );
}
