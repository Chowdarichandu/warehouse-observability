import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  Bell,
  CheckCheck,
  Clock3,
  Radio,
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
  const { rangeQuery } = useFilters();
  const { activity, connected, canOperate } = useApp();
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
        <>
          <span className="positive-text">
            <TrendingUp size={12} /> Completed runs
          </span>
        </>
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
  const hours = data.series.map((s) =>
    new Date(s.hour).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  );
  return (
    <>
      <PageHeader
        title="Pipeline overview"
        description="Every tenant. Every pipeline. One clear picture."
        actions={
          <>
            <span className="updated-label">
              Updated <Time value={data.as_of} relative />
            </span>
            {canOperate && (
              <Link to="/onboarding" className="button primary">
                + Onboard tenant
              </Link>
            )}
          </>
        }
      />
      <div className="kpi-grid">
        {stats.map((stat) => (
          <div className="kpi-card" key={stat.label}>
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
      {k.down > 0 && (
        <div className="attention-banner">
          <span className="attention-icon">
            <ShieldCheck size={17} />
          </span>
          <div>
            <strong>
              {k.down} tenant {k.down === 1 ? 'needs' : 'need'} your attention
            </strong>
            <span>Acme Retail’s replication position is lost. A full resync is required.</span>
          </div>
          <Link to="/tenants/acme_retail">
            Investigate <ArrowRight size={14} />
          </Link>
        </div>
      )}
      <Panel
        title="Tenant health"
        subtitle="Latest status across your four pipelines. Problems appear first."
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
            Run make demo to populate the console with fictional tenants.
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
          subtitle="Completed and active pipeline runs"
          action={<span className="chart-label">RUNS / HOUR</span>}
        >
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
                name: status[0].toUpperCase() + status.slice(1),
                type: 'bar',
                stack: 'runs',
                barMaxWidth: 16,
                itemStyle: {
                  color: STATUS_COLORS[status],
                  borderRadius: status === 'running' ? [3, 3, 0, 0] : 0,
                },
                data: data.series.map((s) => s[status as 'success' | 'failed' | 'running']),
              })),
            }}
          />
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
          subtitle="A starting point for your next investigation"
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
                <strong>Connected to your pipelines</strong>
                <p>The next simulated batch arrives every minute.</p>
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
