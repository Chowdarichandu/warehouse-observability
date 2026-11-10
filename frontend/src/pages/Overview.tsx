import { useQuery } from '@tanstack/react-query';
import { Select } from '../components/Select';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  Bell,
  CheckCheck,
  Clock3,
  Radio,
  Workflow,
  Database,
  ArrowUpRight,
  ShieldCheck,
  TrendingUp,
  Users,
} from 'lucide-react';
import { api, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { Chart } from '../components/Chart';
import { HealthGrid } from '../components/HealthGrid';
import { STATUS_COLORS } from '../components/statusColors';
import {
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Panel,
  TenantLink,
  Time,
  useFilters,
} from '../components/ui';

export function Overview() {
  const { rangeQuery, params, set } = useFilters();
  const navigate = useNavigate();
  const selectedTenant = params.get('activity_tenant') || '';
  const filteredRuns = useQuery({
    queryKey: ['activity-runs', selectedTenant, rangeQuery],
    queryFn: () =>
      api<Schema<'Page_Run_'>>(
        `/runs?${rangeQuery}&tenant=${encodeURIComponent(selectedTenant)}&page_size=200`,
      ),
    enabled: !!selectedTenant,
    placeholderData: undefined,
  });
  const tenantActivity = useQuery({
    queryKey: ['tenant-activity', selectedTenant, rangeQuery],
    queryFn: () => api<Schema<'TenantMetrics'>>(`/tenants/${selectedTenant}/metrics?${rangeQuery}`),
    enabled: !!selectedTenant,
    placeholderData: undefined,
  });
  const activityByHour = new Map(
    (tenantActivity.data?.activity ?? []).map((b) => [
      new Date(b.bucket).toISOString().slice(0, 13),
      b,
    ]),
  );
  const { activity, connected } = useApp();
  const overview = useQuery({
    queryKey: ['overview', rangeQuery],
    queryFn: () => api<Schema<'Overview'>>(`/overview?${rangeQuery}`),
  });
  const tenants = useQuery({
    queryKey: ['tenants'],
    queryFn: () => api<Schema<'Page_Tenant_'>>('/tenants?page_size=200'),
  });
  if (overview.isPending || tenants.isPending) return <Loading />;
  if (overview.error || tenants.error)
    return <ErrorState error={(overview.error || tenants.error)!} />;
  const data = overview.data!;
  const k = data.kpis;
  const stats = [
    {
      label: 'Healthy tenants',
      value: `${k.healthy}`,
      suffix: `/ ${tenants.data!.total}`,
      icon: Users,
      foot: (
        <>
          <span className="danger-text">{k.down} down</span>
          <i /> <span className="warning-text">{k.degraded} degraded</span>
        </>
      ),
    },
    {
      label: 'Success rate',
      value: <NumberValue value={k.success_rate} suffix="%" />,
      icon: CheckCheck,
      foot: (
        <Link
          className="positive-text"
          to={`/runs?status=success&range=${params.get('range') || '24h'}`}
        >
          <TrendingUp size={12} /> Passed runs
        </Link>
      ),
    },
    {
      label: 'Failed runs',
      value: k.failed_runs,
      icon: ShieldCheck,
      foot: <>{k.total_runs.toLocaleString()} total runs in range</>,
    },
    {
      label: 'CDC duration',
      value: <NumberValue value={k.cdc_avg_min} />,
      suffix: 'min',
      icon: Clock3,
      foot: (
        <>
          p95{' '}
          <strong>
            <NumberValue value={k.cdc_p95_min} suffix=" min" />
          </strong>
        </>
      ),
    },
    {
      label: 'SLA compliance',
      value: <NumberValue value={k.sla_compliance} suffix="%" />,
      icon: TrendingUp,
      foot: <>Across active tenant sources</>,
    },
    {
      label: 'Running now',
      value: k.running_now,
      icon: Activity,
      foot: (
        <Link to="/alerts">
          <Bell size={12} /> {k.open_alerts} open alerts <ArrowRight size={12} />
        </Link>
      ),
    },
  ];
  const attention = tenants.data!.items.filter((t) => ['down', 'degraded'].includes(t.health));
  const namesFor = (state: string) =>
    tenants
      .data!.items.filter((t) => t.health === state)
      .map((t) => t.display_name)
      .join(', ') || 'none';
  const stateTip = (state: string, count: number) =>
    `${state[0].toUpperCase() + state.slice(1)} — ${count} tenant${count === 1 ? '' : 's'}: ${namesFor(state)}`;
  const primaryIssue = attention[0];
  const total = tenants.data!.total;
  const healthyPercent = total ? Math.round((k.healthy / total) * 100) : 0;
  const metrics = stats.filter((s) =>
    ['Success rate', 'SLA compliance', 'CDC duration', 'Failed runs'].includes(s.label),
  );
  const hours = data.series.map((s) =>
    new Date(s.hour).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  );
  return (
    <>
      <PageHeader
        title="Pipeline overview"
        description="Tenant health, run reliability, and open issues across your workspace."
        eyebrow="OPERATIONS"
        actions={
          <>
            <span className="updated-label">
              Updated <Time value={data.as_of} relative />
            </span>
          </>
        }
      />
      <section className="workspace-pulse" aria-label="Workspace health summary">
        <div className="pulse-summary">
          <div className="pulse-eyebrow">
            <span
              className="status-dot"
              style={{ background: k.down ? STATUS_COLORS.down : STATUS_COLORS.healthy }}
            />{' '}
            WORKSPACE HEALTH <span className="pulse-current">Current status</span>
          </div>
          <h2
            className="has-tip"
            data-tip={
              attention.length
                ? `Needs attention: ${attention
                    .map(
                      (t) =>
                        `${t.display_name} (${t.health}, last success ${
                          t.last_success_at
                            ? new Date(t.last_success_at).toLocaleString()
                            : 'not recorded'
                        })`,
                    )
                    .join(' · ')}`
                : 'Every tenant is healthy right now.'
            }
          >
            <span>{k.healthy}</span> of {total} tenants healthy
          </h2>
          <p>
            {k.down + k.degraded
              ? `${k.down + k.degraded} tenants need a closer look.`
              : 'No tenants currently need attention.'}{' '}
            {k.running_now} pipeline {k.running_now === 1 ? 'run is' : 'runs are'} in progress.
          </p>
          <div className="health-distribution" aria-label={`${healthyPercent}% of tenants healthy`}>
            {[
              ['healthy', k.healthy],
              ['degraded', k.degraded],
              ['down', k.down],
              ['paused', Math.max(0, total - k.healthy - k.degraded - k.down)],
            ].map(([state, count]) => (
              <span
                key={state}
                className="has-tip"
                data-tip={stateTip(String(state), Number(count))}
                style={{
                  width: `${total ? (Number(count) / total) * 100 : 0}%`,
                  background: STATUS_COLORS[String(state)],
                }}
              />
            ))}
          </div>
          <div className="pulse-breakdown">
            <Link
              to="/tenants?health=healthy"
              className="has-tip"
              data-tip={stateTip('healthy', k.healthy)}
            >
              <i className="status-dot green" />
              {k.healthy} healthy
            </Link>
            <Link
              to="/tenants?health=degraded"
              className="has-tip"
              data-tip={stateTip('degraded', k.degraded)}
            >
              <i className="status-dot amber" />
              {k.degraded} degraded
            </Link>
            <Link to="/tenants?health=down" className="has-tip" data-tip={stateTip('down', k.down)}>
              <i className="status-dot red" />
              {k.down} down
            </Link>
            <span>{healthyPercent}% healthy</span>
          </div>
        </div>
        <div className="pulse-journey">
          <div className="pulse-journey-top">
            <span className="journey-icon">
              <Workflow size={20} />
            </span>
            <span>PIPELINE TOPOLOGY</span>
            <span className="tag">7 DAGs</span>
          </div>
          <h3>Pipeline orchestration</h3>
          <p>Monitor source provisioning, initial loads, and continuous synchronization.</p>
          <div className="journey-mini">
            <span>
              <Database size={13} />
              Provision
            </span>
            <ArrowRight size={12} />
            <span>Initial load</span>
            <ArrowRight size={12} />
            <span>CDC</span>
          </div>
          <div className="pulse-journey-actions">
            <Link to="/pipelines" className="text-link">
              View DAG catalog <ArrowUpRight size={15} />
            </Link>
          </div>
        </div>
      </section>
      <div
        className={`kpi-grid executive-metrics${overview.isPlaceholderData ? ' is-fetching' : ''}`}
      >
        {metrics.map((stat) => (
          <div
            className="kpi-card has-tip"
            key={stat.label}
            data-tip={
              {
                'Success rate': 'Share of pipeline runs that passed in the selected range.',
                'Failed runs': 'Runs that failed in the selected range, out of the total runs.',
                'CDC duration':
                  'Average CDC sync duration in the selected range; p95 is shown below.',
                'SLA compliance': 'Share of active tenant sources inside their freshness SLA.',
              }[stat.label]
            }
          >
            <div className="kpi-label">
              {stat.label}
              <stat.icon size={15} />
            </div>
            <div className="kpi-value">
              {stat.value}
              <span>{stat.suffix}</span>
            </div>
            <div className="kpi-foot">{stat.foot}</div>
          </div>
        ))}
      </div>
      <div className="platform-strip">
        <span className="strip-label">
          <ServerIcon /> PLATFORM HEALTH
        </span>
        {['airflow_scheduler', 'airbyte', 'warehouse', 'collector'].map((name) => {
          const component = data.platform.find((c) => c.component === name);
          return (
            <Link to="/platform" key={name}>
              <span
                className="status-dot"
                style={{ background: STATUS_COLORS[component?.status || 'paused'] }}
              />
              {name === 'airflow_scheduler'
                ? 'Airflow scheduler'
                : name[0].toUpperCase() + name.slice(1)}
              <small>
                {component?.status === 'up' ? 'Operational' : component?.status || 'Unknown'}
              </small>
            </Link>
          );
        })}
        <Link to="/platform" className="strip-more">
          View platform <ArrowRight size={12} />
        </Link>
      </div>
      {primaryIssue && (
        <div className="attention-banner">
          <span className="attention-icon">
            <ShieldCheck size={17} />
          </span>
          <div>
            <strong>
              {k.down + k.degraded} {k.down + k.degraded === 1 ? 'tenant needs' : 'tenants need'}{' '}
              your attention
            </strong>
            <span>
              {primaryIssue.display_name} · {primaryIssue.failures_24h} failed runs in 24 hours.
              Review current evidence before taking action.
            </span>
          </div>
          <Link to={`/tenants/${primaryIssue.tenant_id}`}>
            Investigate <ArrowRight size={14} />
          </Link>
        </div>
      )}
      <Panel
        title="Tenant health"
        subtitle="Latest source pipeline status across your tenants. Issues appear first."
        className={overview.isPlaceholderData ? 'is-fetching' : ''}
        action={
          <div className="inline-flex">
            <span className="legend-dot green" />
            Healthy
            <span className="legend-dot amber" />
            Degraded
            <span className="legend-dot red" />
            Down
            <Link className="text-link margin-left" to="/tenants">
              All tenants <ArrowRight size={13} />
            </Link>
          </div>
        }
      >
        {tenants.data!.items.length ? (
          <HealthGrid tenants={tenants.data!.items} />
        ) : (
          <Empty title="Your workspace is ready">
            Register tenants to begin monitoring. For the offline demo, run make demo.
          </Empty>
        )}
        <div className="panel-footer">
          <span>{tenants.data!.total} tenants · MySQL & MongoDB</span>
          <span>
            <Radio size={12} /> {connected ? 'Updates streaming live' : 'Polling every 30 seconds'}
          </span>
        </div>
      </Panel>
      <div className="two-column charts-row">
        <Panel
          title="Run activity"
          subtitle={
            selectedTenant
              ? 'Passed, failed and active runs for this tenant'
              : 'Passed, failed and active pipeline runs'
          }
          action={
            <div className="activity-controls">
              <Select
                aria-label="Run activity tenant"
                value={selectedTenant}
                onChange={(e) => set('activity_tenant', e.target.value)}
              >
                <option value="">All tenants</option>
                {tenants.data!.items.map((t) => (
                  <option key={t.tenant_id} value={t.tenant_id}>
                    {t.display_name}
                  </option>
                ))}
              </Select>
              {selectedTenant && (
                <Select
                  aria-label="Open run log"
                  value=""
                  disabled={filteredRuns.isPending || !!filteredRuns.error}
                  onChange={(e) => {
                    if (e.target.value) navigate(`${runPath(e.target.value)}?focus=log`);
                  }}
                >
                  <option value="">Select a run log</option>
                  {filteredRuns.data?.items.map((r) => (
                    <option key={r.run_key} value={r.run_key}>
                      {r.source_type} {r.load_type} · {r.status} ·{' '}
                      {new Date(r.started_at || r.collected_at).toLocaleString()}
                    </option>
                  ))}
                </Select>
              )}
            </div>
          }
        >
          {selectedTenant && filteredRuns.isPending ? (
            <Loading />
          ) : selectedTenant && filteredRuns.error ? (
            <ErrorState error={filteredRuns.error} />
          ) : (
            <Chart
              label="Runs per hour by status"
              option={{
                legend: {
                  top: 0,
                  right: 20,
                  itemWidth: 8,
                  itemHeight: 8,
                  textStyle: { color: '#81909f', fontSize: 10 },
                },
                xAxis: {
                  type: 'category',
                  boundaryGap: false,
                  data: hours,
                  axisLine: { show: false },
                  axisTick: { show: false },
                  axisLabel: {
                    color: '#8b98a6',
                    fontSize: 10,
                    interval: Math.max(0, Math.floor(hours.length / 8)),
                  },
                },
                yAxis: {
                  type: 'value',
                  splitLine: { lineStyle: { color: '#8b98a61b', type: 'dashed' } },
                },
                series: ['success', 'failed', 'running'].map((status) => ({
                  name: status === 'success' ? 'Passed' : status[0].toUpperCase() + status.slice(1),
                  type: 'line',
                  smooth: 0.35,
                  symbol: 'circle',
                  symbolSize: 5,
                  lineStyle: { width: 2 },
                  emphasis: { focus: 'series' },
                  showSymbol: false,
                  areaStyle: { opacity: 0.06 },
                  itemStyle: {
                    color: STATUS_COLORS[status],
                    borderRadius: status === 'running' ? [3, 3, 0, 0] : 0,
                  },
                  data: data.series.map((point) =>
                    selectedTenant
                      ? (activityByHour.get(new Date(point.hour).toISOString().slice(0, 13))?.[
                          status as 'success' | 'failed' | 'running'
                        ] ?? 0)
                      : point[status as 'success' | 'failed' | 'running'],
                  ),
                })),
              }}
            />
          )}
        </Panel>
        <Panel
          title="Duration by pipeline"
          subtitle="Average and p95 of successful runs"
          action={
            <Link to="/runs" className="text-link">
              Explore runs <ArrowRight size={12} />
            </Link>
          }
        >
          <div className="duration-summary">
            {data.durations.map((d) => (
              <div className="duration-row" key={d.name}>
                <span>
                  <span
                    className="status-dot"
                    style={{ background: d.name.startsWith('mysql') ? '#268f7b' : '#7591cb' }}
                  />
                  {d.name.replace('mysql', 'MySQL').replace('mongo', 'Mongo')}
                </span>
                <div className="duration-track">
                  <i
                    style={{
                      width: `${Math.min(100, ((d.avg_min || 0) / Math.max(...data.durations.map((v) => v.p95_min || 1))) * 100)}%`,
                    }}
                  />
                  <b
                    style={{
                      left: `${Math.min(98, ((d.p95_min || 0) / Math.max(...data.durations.map((v) => v.p95_min || 1))) * 100)}%`,
                    }}
                  />
                </div>
                <strong>
                  <NumberValue value={d.avg_min} suffix="m" />
                  <small>
                    p95 <NumberValue value={d.p95_min} suffix="m" />
                  </small>
                </strong>
              </div>
            ))}
          </div>
          <div className="duration-legend">
            <span>
              <i />
              Average duration
            </span>
            <span>
              <b />
              95th percentile
            </span>
          </div>
        </Panel>
      </div>
      <Panel
        title="Duration trends & queue capacity"
        subtitle="Successful duration in minutes, split by pipeline. Queue delay measures Airflow capacity."
        className={overview.isPlaceholderData ? 'is-fetching' : ''}
      >
        <Chart
          label="Average duration trend by pipeline"
          option={{
            legend: { top: 0, textStyle: { color: '#81909f', fontSize: 10 } },
            xAxis: {
              type: 'category',
              data: hours,
              axisLabel: {
                color: '#81909f',
                fontSize: 9,
                interval: Math.max(0, Math.floor(hours.length / 8)),
              },
            },
            yAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
            series: (['mysql_cdc', 'mongo_cdc', 'mysql_initial', 'mongo_initial'] as const).map(
              (pipeline, index) => ({
                name: pipeline.replaceAll('_', ' '),
                type: 'line',
                showSymbol: false,
                smooth: true,
                connectNulls: true,
                itemStyle: { color: ['#18956f', '#7297c5', '#a8c7b0', '#b7a5cb'][index] },
                data: data.series.map((point) => point[pipeline]),
              }),
            ),
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
              {data.durations.map((row) => (
                <tr key={row.name}>
                  <td>{row.name}</td>
                  <td>
                    <NumberValue value={row.avg_min} suffix="m" />
                  </td>
                  <td>
                    <NumberValue value={row.p95_min} suffix="m" />
                  </td>
                  <td>
                    <NumberValue value={row.queue_avg_min} suffix="m" />
                  </td>
                  <td>
                    <NumberValue value={row.queue_p95_min} suffix="m" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="two-column bottom-row">
        <Panel
          title="Recent failures"
          subtitle="The most recent failed runs across tenants"
          action={
            <Link className="text-link" to="/runs?status=failed">
              View failed runs <ArrowRight size={12} />
            </Link>
          }
        >
          {data.recent_failures.length ? (
            <div className="failure-list">
              {data.recent_failures.map((run) => (
                <Link to={runPath(run.run_key)} key={run.run_key}>
                  <span className="failure-icon">
                    <ArrowDownRight size={16} />
                  </span>
                  <div>
                    <strong>{run.tenant_id.replaceAll('_', ' ')}</strong>
                    <small>{run.error_class || run.failed_stage}</small>
                  </div>
                  <span className="tag">
                    {run.source_type} {run.load_type}
                  </span>
                  <Time value={run.started_at} relative />
                  <ArrowRight size={14} />
                </Link>
              ))}
            </div>
          ) : (
            <Empty title="No failures in this range" />
          )}
        </Panel>
        <Panel
          title="Live activity"
          subtitle="Events from the collector and alert engine"
          action={
            <span className="live-mini">
              <span className="pulse-dot" />
              LIVE
            </span>
          }
        >
          <div className="activity-list">
            {activity.length ? (
              activity.slice(0, 6).map((event) => (
                <div key={event.id}>
                  <span
                    className="activity-dot"
                    style={{ background: STATUS_COLORS[event.status || 'running'] }}
                  />
                  <div>
                    <strong>
                      {event.tenant ? <TenantLink id={event.tenant} /> : 'Platform health updated'}
                    </strong>
                    <small>
                      {event.event.replaceAll('.', ' · ')} {event.status && `· ${event.status}`}
                    </small>
                  </div>
                  <time>
                    {event.at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </time>
                </div>
              ))
            ) : (
              <div className="activity-waiting">
                <Radio size={26} />
                <strong>
                  {connected ? 'Ready for the next update' : 'Monitoring with automatic refresh'}
                </strong>
                <p>
                  {connected
                    ? 'New run and alert events will appear here.'
                    : 'Your workspace refreshes every 30 seconds while the live stream reconnects.'}
                </p>
              </div>
            )}
          </div>
        </Panel>
      </div>
    </>
  );
}
function ServerIcon() {
  return (
    <span className="server-icon">
      <i />
      <i />
    </span>
  );
}
