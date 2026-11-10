import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  Lock,
  Pause,
  Play,
  RefreshCw,
  Search,
  Settings2,
} from 'lucide-react';
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
  Source,
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
                  <th>Analytics</th>
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
                    <td>
                      {t.analytics_eligible ? (
                        <span className="wf-status wf-success">Unlocked</span>
                      ) : (
                        <span className="wf-status wf-locked">Locked</span>
                      )}
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

function stageLabel(status: string) {
  switch (status) {
    case 'success':
      return 'Passed';
    case 'running':
      return 'Running';
    case 'failed':
      return 'Failed';
    case 'ready':
      return 'Ready';
    case 'locked':
      return 'Locked';
    default:
      return 'Not started';
  }
}

function WorkflowPanel({ tenantId }: { tenantId: string }) {
  const { canOperate, notify, runtime } = useApp();
  const client = useQueryClient();
  const workflow = useQuery({
    queryKey: ['workflow', tenantId],
    queryFn: () => api<Schema<'WorkflowState'>>(`/tenants/${tenantId}/workflow`),
    refetchInterval: (q) => {
      const data = q.state.data;
      const busy =
        data?.sources.some((s) => s.initial_status === 'running' || s.cdc_status === 'running') ||
        data?.analytics.some((a) => a.last_status === 'started');
      return busy ? 4000 : 15000;
    },
  });
  const trigger = useMutation({
    mutationFn: (dag: string) =>
      api<Schema<'Message'>>(`/tenants/${tenantId}/trigger`, {
        method: 'POST',
        body: JSON.stringify({ dag }),
      }),
    onSuccess: (result) => {
      notify(result.message);
      void client.invalidateQueries({ queryKey: ['workflow', tenantId] });
      void client.invalidateQueries({ queryKey: ['timeline', tenantId] });
    },
    onError: (e) => notify(e.message),
  });
  if (workflow.isPending)
    return (
      <Panel title="Workflows">
        <Loading />
      </Panel>
    );
  if (workflow.error || !workflow.data)
    return (
      <Panel title="Workflows">
        <ErrorState error={workflow.error || new Error('Workflow information is unavailable.')} />
      </Panel>
    );
  const data = workflow.data;
  return (
    <Panel
      title="Workflows"
      subtitle="Source pipelines are managed automatically. Analytics becomes available after MySQL initial load succeeds; manual analytics actions are simulated in demo mode."
    >
      <div className="wf-grid">
        {data.sources.map((source) => {
          const initialPassed = source.initial_status === 'success';
          return (
            <div className="wf-card" key={source.source}>
              <div className="wf-card-head">
                <Source source={source.source} />
                <strong>{source.source === 'mysql' ? 'MySQL' : 'MongoDB'} pipeline</strong>
              </div>
              <div className="wf-stage">
                <div className="wf-stage-info">
                  <span className="wf-stage-name">1 · Initial load</span>
                  <span className={`wf-status wf-${source.initial_status}`}>
                    {stageLabel(source.initial_status)}
                  </span>
                  {source.last_initial_at && (
                    <small>
                      Last run <Time value={source.last_initial_at} relative />
                    </small>
                  )}
                </div>
                <span className="wf-auto">Managed by onboarding</span>
              </div>
              <div className="wf-arrow">
                <ArrowRight size={14} />
                <span>
                  {initialPassed
                    ? 'Initial load passed — this source now feeds CDC'
                    : 'CDC unlocks when the initial load passes'}
                </span>
              </div>
              <div className="wf-stage">
                <div className="wf-stage-info">
                  <span className="wf-stage-name">2 · CDC sync</span>
                  <span className={`wf-status wf-${source.cdc_status}`}>
                    {stageLabel(source.cdc_status)}
                  </span>
                  {source.last_cdc_at && (
                    <small>
                      Last run <Time value={source.last_cdc_at} relative />
                    </small>
                  )}
                </div>
                <span className="wf-auto">Managed by schedule</span>
              </div>
            </div>
          );
        })}
        <div className="wf-card wf-analytics">
          <div className="wf-card-head">
            <BarChart3 size={16} />
            <strong>Analytics</strong>
            <span className={`wf-status ${data.analytics_eligible ? 'wf-success' : 'wf-locked'}`}>
              {data.analytics_eligible ? 'Unlocked' : 'Locked'}
            </span>
          </div>
          {!data.analytics_eligible ? (
            <p className="wf-note">
              <Lock size={13} /> Analytics becomes available the moment this tenant’s MySQL initial
              load passes.
            </p>
          ) : (
            data.analytics.map((dag) => (
              <div className="wf-stage" key={dag.id}>
                <div className="wf-stage-info">
                  <span className="wf-stage-name">{dag.name}</span>
                  {dag.last_at ? (
                    <small>
                      Last run <Time value={dag.last_at} relative /> ·{' '}
                      {dag.last_status === 'ok'
                        ? 'Passed'
                        : dag.last_status === 'started'
                          ? 'Running'
                          : dag.last_status}
                    </small>
                  ) : (
                    <small>Not run yet</small>
                  )}
                </div>
                <button
                  className="button small"
                  disabled={
                    !canOperate ||
                    runtime.mode !== 'demo' ||
                    trigger.isPending ||
                    dag.last_status === 'started'
                  }
                  title={
                    runtime.mode !== 'demo'
                      ? 'Manual analytics actions are only available in demo mode'
                      : undefined
                  }
                  onClick={() => trigger.mutate(dag.id)}
                >
                  <Play size={13} /> Simulate
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </Panel>
  );
}

export function TenantDetail() {
  const { id = '' } = useParams();
  const { range, rangeQuery, params } = useFilters();
  const { runtime, isAdmin, notify } = useApp();
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
  const pipelineKeys = (
    [
      ['mysql', 'cdc', '#18956f'],
      ['mongo', 'cdc', '#7297c5'],
      ['mysql', 'initial', '#a8c7b0'],
      ['mongo', 'initial', '#b7a5cb'],
    ] as const
  ).filter(([source]) => (source === 'mysql' ? config.has_mysql : config.has_mongo));
  const percentile = (values: number[], q: number) => {
    if (!values.length) return null;
    const ordered = [...values].sort((a, b) => a - b);
    return ordered[Math.min(ordered.length - 1, Math.ceil(q * ordered.length) - 1)];
  };
  const average = (values: number[]) =>
    values.length ? values.reduce((sum, v) => sum + v, 0) / values.length : null;
  const minutes = (seconds: number | null) => (seconds == null ? null : seconds / 60);
  const metricRows = pipelineKeys.map(([source, load]) => {
    const own = runs.filter((r) => r.source_type === source && r.load_type === load);
    const durations = own
      .filter((r) => r.status === 'success' && r.duration_s != null)
      .map((r) => r.duration_s!);
    const queues = own.filter((r) => r.queue_delay_s != null).map((r) => r.queue_delay_s!);
    return {
      name: `${source} ${load}`,
      count: own.length,
      avg: minutes(average(durations)),
      p95: minutes(percentile(durations, 0.95)),
      queueAvg: minutes(average(queues)),
      queueP95: minutes(percentile(queues, 0.95)),
    };
  });
  const hourBuckets = new Map<string, Map<string, number[]>>();
  for (const run of runs) {
    if (run.status !== 'success' || run.duration_s == null || !run.started_at) continue;
    const hour = new Date(run.started_at);
    hour.setMinutes(0, 0, 0);
    const key = hour.toISOString();
    if (!hourBuckets.has(key)) hourBuckets.set(key, new Map());
    const label = `${run.source_type} ${run.load_type}`;
    const bucket = hourBuckets.get(key)!;
    bucket.set(label, [...(bucket.get(label) || []), run.duration_s / 60]);
  }
  const metricHours = [...hourBuckets.keys()].sort();
  const formatMinutes = (value: number | null) =>
    value == null ? '—' : `${Math.round(value * 10) / 10}m`;
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
              disabled={!isAdmin || !runtime.live_actions_enabled || update.isPending}
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
      {runtime.mode === 'demo' && id === 'acme_retail' && health.health === 'down' && (
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
      <WorkflowPanel tenantId={id} />
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
          <span>Avg run duration</span>
          <strong>
            {formatMinutes(
              minutes(
                average(
                  runs
                    .filter((r) => r.status === 'success' && r.duration_s != null)
                    .map((r) => r.duration_s!),
                ),
              ),
            )}
            <small> per successful run</small>
          </strong>
        </div>
        <div>
          <span>Open alerts</span>
          <Link to="/alerts">
            {alerts.length} <ArrowRight size={13} />
          </Link>
        </div>
      </div>
      <Panel
        title="Duration & queue metrics"
        subtitle="Successful duration in minutes, split by pipeline for this tenant. Queue delay measures Airflow capacity."
      >
        {runs.length ? (
          <>
            <Chart
              label={`Average duration trend by pipeline for ${config.display_name}`}
              option={{
                legend: { top: 0, textStyle: { color: '#81909f', fontSize: 10 } },
                xAxis: {
                  type: 'category',
                  data: metricHours.map((h) =>
                    new Date(h).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
                  ),
                  axisLabel: {
                    color: '#81909f',
                    fontSize: 9,
                    interval: Math.max(0, Math.floor(metricHours.length / 8)),
                  },
                },
                yAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
                series: pipelineKeys.map(([source, load, color]) => ({
                  name: `${source} ${load}`,
                  type: 'line',
                  showSymbol: false,
                  smooth: true,
                  connectNulls: true,
                  itemStyle: { color },
                  data: metricHours.map((h) => {
                    const values = hourBuckets.get(h)?.get(`${source} ${load}`);
                    const avg = average(values || []);
                    return avg == null ? null : Math.round(avg * 100) / 100;
                  }),
                })),
              }}
            />
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Pipeline</th>
                    <th>Duration · avg</th>
                    <th>Duration · p95</th>
                    <th>Queue delay · avg</th>
                    <th>Queue delay · p95</th>
                  </tr>
                </thead>
                <tbody>
                  {metricRows.map((row) => (
                    <tr key={row.name}>
                      <td>{row.name}</td>
                      {row.count === 0 ? (
                        <td colSpan={4} className="muted">
                          No runs in the selected range
                          {row.name.endsWith('initial')
                            ? ' — initial loads run once, at onboarding'
                            : ''}
                        </td>
                      ) : (
                        <>
                          <td>{formatMinutes(row.avg)}</td>
                          <td>{formatMinutes(row.p95)}</td>
                          <td>{formatMinutes(row.queueAvg)}</td>
                          <td>{formatMinutes(row.queueP95)}</td>
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="muted">No runs in the selected range for this tenant yet.</p>
        )}
      </Panel>
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
          {config.has_mysql && (
            <div>
              <span>MySQL layout</span>
              <strong>
                Dedicated database <code>{config.tenant_id}</code> — one database per tenant
              </strong>
            </div>
          )}
          {config.has_mongo && (
            <div>
              <span>MongoDB layout</span>
              <strong>
                Shared cluster — documents carry the tenant key{' '}
                <code>tenant_id: "{config.tenant_id}"</code>
              </strong>
            </div>
          )}
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
