import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ArrowRight, Pause, Play, RefreshCw, Search, Settings2 } from 'lucide-react';
import { api, queryString, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { Chart } from '../components/Chart';
import { HealthGrid } from '../components/HealthGrid';
import { StatusPill } from '../components/StatusPill';
import { STATUS_COLORS } from '../components/statusColors';
import {
  Back,
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Pagination,
  Panel,
  Time,
  useFilters,
} from '../components/ui';

export function Tenants() {
  const { params, set, page } = useFilters();
  const { canOperate } = useApp();
  const qs = queryString({ q: params.get('q') || '', health: params.get('health') || '', page });
  const query = useQuery({
    queryKey: ['tenants', qs],
    queryFn: () => api<Schema<'Page_Tenant_'>>(`/tenants?${qs}`),
  });
  return (
    <>
      <PageHeader
        title="Tenants"
        description="Health, freshness, and pipeline status for every client."
        actions={
          canOperate && (
            <Link className="button primary" to="/onboarding">
              + Onboard tenant
            </Link>
          )
        }
      />
      <Panel>
        <div className="filter-bar">
          <label className="search-field">
            <Search size={15} />
            <input
              placeholder="Search tenants…"
              aria-label="Search tenants"
              value={params.get('q') || ''}
              onChange={(e) => set('q', e.target.value)}
            />
          </label>
          <select
            aria-label="Filter by health"
            value={params.get('health') || ''}
            onChange={(e) => set('health', e.target.value)}
          >
            <option value="">All health states</option>
            {['healthy', 'degraded', 'down', 'paused', 'onboarding'].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
          <span className="filter-count">{query.data?.total ?? '…'} tenants</span>
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data.items.length ? (
          <>
            <HealthGrid tenants={query.data.items} />
            <Pagination
              total={query.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
          </>
        ) : (
          <Empty title="No tenants match your search" />
        )}
      </Panel>
      {query.data && (
        <Panel
          title="Service levels"
          subtitle="Seven-day SLA compliance and successful-run duration"
        >
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th>SLA compliance · 7d</th>
                  <th>Average duration</th>
                  <th>Failures · 24h</th>
                  <th>Last success</th>
                </tr>
              </thead>
              <tbody>
                {query.data.items.map((t) => (
                  <tr key={t.tenant_id}>
                    <td>
                      <Link className="text-link" to={`/tenants/${t.tenant_id}`}>
                        {t.display_name}
                      </Link>
                    </td>
                    <td>
                      <NumberValue value={t.sla_compliance} suffix="%" />
                    </td>
                    <td>
                      <NumberValue value={t.avg_duration_min} suffix=" min" />
                    </td>
                    <td>{t.failures_24h}</td>
                    <td>
                      <Time value={t.last_success_at} relative />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  );
}

export function TenantDetail() {
  const { id = '' } = useParams();
  const { range, rangeQuery, params } = useFilters();
  const { isAdmin, notify } = useApp();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['tenant', id],
    queryFn: () => api<Schema<'TenantDetail'>>(`/tenants/${id}`),
  });
  const timeline = useQuery({
    queryKey: ['timeline', id, rangeQuery],
    queryFn: () => api<Schema<'Page_Run_'>>(`/tenants/${id}/timeline?${rangeQuery}&page_size=200`),
  });
  const update = useMutation({
    mutationFn: (body: Schema<'TenantPatch'>) =>
      api<Schema<'Message'>>(`/tenants/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: (result) => {
      notify(result.message);
      void client.invalidateQueries();
    },
    onError: (e) => notify(e.message),
  });
  const resync = useMutation({
    mutationFn: () => api<Schema<'Message'>>(`/tenants/${id}/resync`, { method: 'POST' }),
    onSuccess: (result) => {
      notify(result.message);
      void client.invalidateQueries();
    },
    onError: (e) => notify(e.message),
  });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const { config, health, tables, alerts, errors, schema_changes, events } = query.data;
  const runs = timeline.data?.items || [];
  const sorted = [...runs].sort((a, b) => (a.started_at || '').localeCompare(b.started_at || ''));
  return (
    <>
      <Back to="/tenants">All tenants</Back>
      <PageHeader
        title={config.display_name}
        description={`${id} · ${config.warehouse_schema} · Created ${new Date(config.created_at).toLocaleDateString()}`}
        actions={
          <>
            <StatusPill status={health.health} />
            <button
              className="button"
              disabled={!isAdmin || update.isPending}
              title={!isAdmin ? 'Administrator role required' : ''}
              onClick={() =>
                update.mutate({ status: config.status === 'paused' ? 'active' : 'paused' })
              }
            >
              {config.status === 'paused' ? <Play size={14} /> : <Pause size={14} />}
              {config.status === 'paused' ? 'Resume tenant' : 'Pause tenant'}
            </button>
            <button
              className="icon-button"
              aria-label="Tenant settings"
              disabled={!isAdmin}
              onClick={() => setSettingsOpen(!settingsOpen)}
            >
              <Settings2 size={17} />
            </button>
          </>
        }
      />
      {id === 'acme_retail' && health.health === 'down' && (
        <div className="notice danger">
          <RefreshCw size={21} />
          <div>
            <strong>MySQL replication position is no longer available</strong>
            <p>
              CDC has failed since 02:00. The binlog was purged. A task retry does not restore the
              missing position; a full resync is required.
            </p>
          </div>
          <button
            className="button"
            disabled={!isAdmin || resync.isPending}
            onClick={() => resync.mutate()}
          >
            Simulate resync
          </button>
        </div>
      )}
      {settingsOpen && (
        <Panel title="Tenant settings">
          <form
            className="settings-form"
            onSubmit={(e) => {
              e.preventDefault();
              const data = new FormData(e.currentTarget);
              update.mutate({
                freshness_sla_min: Number(data.get('sla')),
                owner_email: String(data.get('owner')),
              });
            }}
          >
            <label>
              Freshness SLA (minutes)
              <input
                type="number"
                name="sla"
                min="5"
                max="10080"
                defaultValue={config.freshness_sla_min}
              />
            </label>
            <label>
              Owner email
              <input type="email" name="owner" placeholder="owner@company.example" />
            </label>
            <button className="button primary" disabled={update.isPending}>
              Save settings
            </button>
          </form>
        </Panel>
      )}
      <div className="detail-kpis">
        <div>
          <span>Tenant status</span>
          <span className="tag">{config.status}</span>
        </div>
        <div>
          <span>Freshness</span>
          <strong>
            <NumberValue value={health.worst_stale_min} suffix=" min" />
            <small> / {config.freshness_sla_min}m SLA</small>
          </strong>
        </div>
        <div>
          <span>SLA compliance · 7d</span>
          <strong>
            <NumberValue value={health.sla_compliance} suffix="%" />
          </strong>
        </div>
        <div>
          <span>Failed runs · 24h</span>
          <strong>{health.failures_24h}</strong>
        </div>
        <div>
          <span>Open alerts</span>
          <Link to="/alerts">
            {alerts.length} <ArrowRight size={13} />
          </Link>
        </div>
      </div>
      <Panel
        title="Pipeline timeline"
        subtitle="Select a run to inspect its metrics and log."
        action={
          <div className="inline-flex">
            <StatusPill status="success" />
            <StatusPill status="failed" />
            <StatusPill status="running" />
          </div>
        }
      >
        {timeline.isPending ? (
          <Loading />
        ) : timeline.error ? (
          <ErrorState error={timeline.error} />
        ) : runs.length ? (
          <Swimlane
            runs={runs}
            range={range}
            startValue={params.get('from')}
            endValue={params.get('to')}
          />
        ) : (
          <Empty title="No runs in this range" />
        )}
        {timeline.data && timeline.data.total > 200 && (
          <div className="panel-footer">
            Showing the latest 200 of {timeline.data.total} runs.{' '}
            <Link to={`/runs?tenant=${id}&range=${range}`}>Explore all runs →</Link>
          </div>
        )}
      </Panel>
      <div className="two-column">
        <Panel
          title="Duration against baseline"
          subtitle="Successful duration in minutes · dashed line is the pipeline median"
        >
          <Chart
            label="Tenant run duration"
            option={{
              xAxis: {
                type: 'category',
                data: sorted.map((r) =>
                  new Date(r.started_at!).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  }),
                ),
                axisLabel: { color: '#81909f', fontSize: 10 },
              },
              yAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
              series: ['mysql:cdc', 'mysql:initial', 'mongo:cdc', 'mongo:initial'].map(
                (pipeline, index) => {
                  const [source, load] = pipeline.split(':');
                  const baseline = query.data.baselines?.find(
                    (b) => b.source_type === source && b.load_type === load,
                  );
                  return {
                    name: `${source} ${load}`,
                    type: 'line',
                    showSymbol: false,
                    smooth: true,
                    connectNulls: true,
                    itemStyle: { color: ['#18956f', '#87bda6', '#7297c5', '#b0c0d9'][index] },
                    markLine: {
                      symbol: 'none',
                      silent: true,
                      label: { show: false },
                      lineStyle: { type: 'dashed', opacity: 0.6 },
                      data: baseline ? [{ yAxis: baseline.median_s / 60 }] : [],
                    },
                    data: sorted.map((r) =>
                      r.source_type === source && r.load_type === load && r.status === 'success'
                        ? (r.duration_s || 0) / 60
                        : null,
                    ),
                  };
                },
              ),
            }}
          />
        </Panel>
        <Panel title="Rows synced" subtitle="Volume per run in the selected range">
          <Chart
            label="Rows synced per run"
            option={{
              xAxis: {
                type: 'category',
                data: sorted.map((r) =>
                  new Date(r.started_at!).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  }),
                ),
                axisLabel: { color: '#81909f', fontSize: 10 },
              },
              yAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
              series: [
                {
                  type: 'bar',
                  barMaxWidth: 10,
                  itemStyle: { color: '#77ac9d', borderRadius: [2, 2, 0, 0] },
                  data: sorted.map((r) => r.rows_synced || 0),
                },
              ],
            }}
          />
        </Panel>
      </div>
      <div className="two-column">
        <Panel
          title="Recent errors"
          action={
            <Link className="text-link" to={`/runs?tenant=${id}&status=failed`}>
              All failures <ArrowRight size={12} />
            </Link>
          }
        >
          {errors.length ? (
            errors.slice(0, 5).map((error) => (
              <Link className="error-item" key={error.run_key} to={runPath(error.run_key)}>
                <StatusPill status="failed" />
                <div>
                  <strong className="mono">{error.error_class}</strong>
                  <p>{error.hint}</p>
                </div>
                <ArrowRight size={15} />
              </Link>
            ))
          ) : (
            <Empty title="No recent errors" />
          )}
        </Panel>
        <Panel title="Warehouse freshness" subtitle="Latest catalog snapshot per table">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Table</th>
                  <th>Row count</th>
                  <th>Last loaded</th>
                </tr>
              </thead>
              <tbody>
                {tables.map((table) => (
                  <tr key={table.table_name}>
                    <td className="mono">{table.table_name}</td>
                    <td>
                      <NumberValue value={table.row_count} />
                    </td>
                    <td>
                      <Time value={table.last_loaded_at} relative />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!tables.length && <Empty title="Waiting for the first warehouse snapshot" />}
        </Panel>
      </div>
      <Panel title="Connections & configuration">
        <div className="config-grid">
          <div>
            <span>Owner</span>
            <strong>{config.owner_email || 'Unassigned'}</strong>
          </div>
          <div>
            <span>Warehouse schema</span>
            <code>{config.warehouse_schema}</code>
          </div>
          {Object.entries(config.airbyte_connections).map(([key, value]) => (
            <div key={key}>
              <span>{key.replaceAll('_', ' ')}</span>
              <code>{value}</code>
            </div>
          ))}
        </div>
      </Panel>
      {!!schema_changes.length && (
        <Panel title="Schema changes">
          {schema_changes.map((change) => (
            <div className="change-row" key={change.table_name}>
              <code>{change.table_name}</code>
              <span className="positive-text">+ {change.added.join(', ')}</span>
              <Time value={change.checked_at} />
            </div>
          ))}
        </Panel>
      )}
      {!!events.length && (
        <Panel title="Onboarding history">
          <div className="steps-list">
            {events
              .filter((e) => e.status === 'ok')
              .map((e) => (
                <div key={e.id}>
                  <StatusPill status="success" />
                  <strong>{e.step}</strong>
                  <Time value={e.at} />
                </div>
              ))}
          </div>
        </Panel>
      )}
    </>
  );
}

function Swimlane({
  runs,
  range,
  startValue,
  endValue,
}: {
  runs: Schema<'Run'>[];
  range: string;
  startValue: string | null;
  endValue: string | null;
}) {
  const end = range === 'custom' && endValue ? new Date(endValue).getTime() : Date.now();
  const hours =
    ({ '1h': 1, '6h': 6, '24h': 24, '7d': 168, '30d': 720 } as Record<string, number>)[range] || 24;
  const start =
    range === 'custom' && startValue ? new Date(startValue).getTime() : end - hours * 3600000;
  return (
    <div className="swimlane">
      <div className="swimlane-axis">
        <span />
        {[0, 1, 2, 3, 4].map((n) => (
          <span key={n}>
            {new Date(start + ((end - start) * n) / 4).toLocaleString([], {
              weekday: hours > 24 ? 'short' : undefined,
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
        ))}
      </div>
      {['mysql:cdc', 'mysql:initial', 'mongo:cdc', 'mongo:initial'].map((pipeline) => {
        const [source, load] = pipeline.split(':');
        return (
          <div className="swimlane-row" key={pipeline}>
            <strong>
              {source === 'mysql' ? 'MySQL' : 'Mongo'}
              <small>{load.toUpperCase()}</small>
            </strong>
            <div className="swimlane-track">
              {runs
                .filter((r) => r.source_type === source && r.load_type === load)
                .map((r) => {
                  const left = Math.max(
                    0,
                    ((new Date(r.started_at!).getTime() - start) / (end - start)) * 100,
                  );
                  const width = Math.max(
                    0.8,
                    (((r.ended_at ? new Date(r.ended_at).getTime() : end) -
                      new Date(r.started_at!).getTime()) /
                      (end - start)) *
                      100,
                  );
                  return (
                    <Link
                      key={r.run_key}
                      to={runPath(r.run_key)}
                      className="run-block"
                      aria-label={`${source} ${load} ${r.status} run`}
                      title={`${source} ${load}: ${r.status} · ${new Date(r.started_at!).toLocaleString()}`}
                      style={{
                        left: `${Math.min(99, left)}%`,
                        width: `${Math.min(width, 100 - left)}%`,
                        background: STATUS_COLORS[r.status],
                      }}
                    />
                  );
                })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
