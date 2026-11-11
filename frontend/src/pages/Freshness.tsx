import { useQuery } from '@tanstack/react-query';
import { ArrowDown, GitBranch, Plus, Table2 } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { StatusPill } from '../components/StatusPill';
import { STATUS_COLORS } from '../components/statusColors';
import {
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Pagination,
  Panel,
  Source,
  TenantLink,
  Time,
  formatDuration,
  useFilters,
} from '../components/ui';

export function Freshness() {
  const { page, set } = useFilters();
  const query = useQuery({
    queryKey: ['freshness', page],
    queryFn: () => api<Schema<'Page_Freshness_'>>(`/freshness?page=${page}`),
  });
  const volume = useQuery({
    queryKey: ['volume'],
    queryFn: () => api<Schema<'Page_Change_'>>('/volume-anomalies'),
  });
  const schema = useQuery({
    queryKey: ['schema'],
    queryFn: () => api<Schema<'Page_Change_'>>('/schema-changes'),
  });
  const forecast = useQuery({
    queryKey: ['forecast'],
    queryFn: () => api<Schema<'Page_Forecast_'>>('/forecast?page_size=100'),
  });
  const atRisk = (forecast.data?.items ?? []).filter((item) => item.state !== 'safe');
  return (
    <>
      <PageHeader
        title="Freshness & volume"
        description="Current data freshness for every source, plus every recorded volume anomaly and schema change. Freshness is a live snapshot — it does not follow the global time range."
      />
      {atRisk.length > 0 && (
        <Panel
          title="SLA breach forecast"
          subtitle="Projected from data age, the SLA and each tenant's run interval, assuming the next run fails."
          className={forecast.isPlaceholderData ? 'is-fetching' : ''}
        >
          <ul className="forecast-list">
            {atRisk.map((item) => (
              <li key={item.tenant_id}>
                <StatusPill status={item.state === 'breached' ? 'down' : 'degraded'} />
                <span>
                  <TenantLink id={item.tenant_id} /> —{' '}
                  {item.state === 'breached'
                    ? `SLA already breached: data is ${formatDuration(item.data_age_min * 60)} old against a ${item.freshness_sla_min}m SLA.`
                    : `will breach SLA in about ${Math.max(1, Math.round(item.breach_in_min ?? 0))} min if the next run fails.`}
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      <Panel
        title="Data freshness"
        subtitle="Time since the last successful sync, measured against each source’s SLA."
        action={<span className="tag">5-MINUTE SLA BUCKETS</span>}
        className={query.isPlaceholderData ? 'is-fetching' : ''}
      >
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Tenant</th>
                    <th>Source</th>
                    <th>Freshness / SLA</th>
                    <th>Last successful sync</th>
                    <th>SLA · 7 days</th>
                    <th>SLA · 30 days</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((row) => {
                    const status =
                      row.minutes_stale == null || row.minutes_stale > row.freshness_sla_min
                        ? 'down'
                        : row.minutes_stale > row.freshness_sla_min * 0.75
                          ? 'degraded'
                          : 'healthy';
                    return (
                      <tr key={`${row.tenant_id}:${row.source_type}`}>
                        <td>
                          <TenantLink id={row.tenant_id} />
                        </td>
                        <td>
                          <Source source={row.source_type} />
                        </td>
                        <td>
                          <div
                            className="freshness-meter has-tip"
                            data-tip={`${row.minutes_stale ?? '—'} min since the last successful sync, of a ${row.freshness_sla_min} min SLA`}
                          >
                            <span style={{ color: STATUS_COLORS[status] }}>
                              {row.minutes_stale == null
                                ? '—'
                                : row.minutes_stale < 60
                                  ? `${row.minutes_stale}m`
                                  : formatDuration(row.minutes_stale * 60)}{' '}
                              <small>/ {row.freshness_sla_min}m</small>
                            </span>
                            <div className="mini-track">
                              <i
                                style={{
                                  background: STATUS_COLORS[status],
                                  width: `${Math.min(100, ((row.minutes_stale || 0) / row.freshness_sla_min) * 100)}%`,
                                }}
                              />
                            </div>
                            <StatusPill status={status} />
                          </div>
                        </td>
                        <td>
                          <Time value={row.last_success_at} relative />
                        </td>
                        <td>
                          <NumberValue value={row.sla_7d} suffix="%" />
                        </td>
                        <td>
                          <NumberValue value={row.sla_30d} suffix="%" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              total={query.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
            <div className="panel-footer">
              SLA is computed from recorded run history. Older, unobserved buckets count as
              non-compliant in the 30-day metric.
            </div>
          </>
        )}
      </Panel>
      <div className="two-column">
        <Panel
          title="Volume anomalies"
          subtitle="Drops over 30%, or growth over 5× the seven-day average and 5% above the previous count."
          action={<Table2 size={17} />}
          className={volume.isPlaceholderData ? 'is-fetching' : ''}
        >
          {volume.isPending ? (
            <Loading />
          ) : volume.error ? (
            <ErrorState error={volume.error} />
          ) : volume.data.items.length ? (
            volume.data.items.map((change) => (
              <div
                className="anomaly-card"
                key={`${change.tenant_id}:${change.table_name}:${change.checked_at}`}
              >
                <div className="inline-flex">
                  <TenantLink id={change.tenant_id} />
                  <span className="tag mono">{change.table_name}</span>
                </div>
                <div className="anomaly-value">
                  <ArrowDown size={21} />
                  <NumberValue value={change.change_pct} suffix="%" />
                  <small>row count</small>
                </div>
                <p>
                  <NumberValue value={change.previous_count} /> →{' '}
                  <NumberValue value={change.row_count} /> rows
                </p>
                <Time value={change.checked_at} />
              </div>
            ))
          ) : (
            <Empty title="No volume anomalies" />
          )}
        </Panel>
        <Panel
          title="Schema drift"
          subtitle="Column changes detected between consecutive catalog snapshots."
          action={<GitBranch size={17} />}
          className={schema.isPlaceholderData ? 'is-fetching' : ''}
        >
          {schema.isPending ? (
            <Loading />
          ) : schema.error ? (
            <ErrorState error={schema.error} />
          ) : schema.data.items.length ? (
            schema.data.items.map((change) => (
              <div
                className="schema-card"
                key={`${change.tenant_id}:${change.table_name}:${change.checked_at}`}
              >
                <div className="inline-flex">
                  <TenantLink id={change.tenant_id} />
                  <span className="tag mono">{change.table_name}</span>
                </div>
                {change.added?.map((c) => (
                  <p className="positive-text" key={c}>
                    <Plus size={14} />
                    <code>{c}</code>
                    <span className="tag">column added</span>
                  </p>
                ))}
                {change.removed?.map((c) => (
                  <p className="danger-text" key={c}>
                    − {c} removed
                  </p>
                ))}
                {change.type_changed?.map((c) => <p key={c}>{c}</p>)}
                <Time value={change.checked_at} />
              </div>
            ))
          ) : (
            <Empty title="No schema changes" />
          )}
        </Panel>
      </div>
    </>
  );
}
