import './overview.css';
import { cssColor } from '../styles/colors';
import { useQuery } from '@tanstack/react-query';
import { Select } from '../components/Select';
import { Activity, CheckCheck, Clock3, ShieldCheck, TrendingUp, Users } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { Chart } from '../components/Chart';
import { StatusPill } from '../components/StatusPill';
import { STATUS_COLORS } from '../components/statusColors';
import {
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Panel,
  Time,
  useFilters,
} from '../components/ui';

export function MetricsOverview() {
  const { rangeQuery, params, set } = useFilters();
  const selectedTenant = params.get('activity_tenant') || '';
  const metrics = useQuery({
    queryKey: ['metrics-overview', rangeQuery],
    queryFn: () => api<Schema<'MetricsOverview'>>(`/metrics/overview?${rangeQuery}`),
  });
  const tenants = useQuery({
    queryKey: ['metrics-tenants'],
    queryFn: () => api<Schema<'Page_MetricsTenant_'>>('/metrics/tenants?page_size=200'),
  });
  const tenantMetrics = useQuery({
    queryKey: ['metrics-tenant', selectedTenant, rangeQuery],
    queryFn: () =>
      api<Schema<'TenantMetrics'>>(
        `/tenants/${encodeURIComponent(selectedTenant)}/metrics?${rangeQuery}`,
      ),
    enabled: !!selectedTenant,
  });
  if (metrics.isPending || tenants.isPending || (selectedTenant && tenantMetrics.isPending))
    return <Loading />;
  if (metrics.error || tenants.error || tenantMetrics.error)
    return <ErrorState error={(metrics.error || tenants.error || tenantMetrics.error)!} />;

  const data = metrics.data!;
  const k = data.kpis;
  const tenantItems = tenants.data!.items;
  const tenant = tenantItems.find((item) => item.tenant_id === selectedTenant);
  const activityByHour = new Map(
    (tenantMetrics.data?.activity ?? []).map((bucket) => [
      new Date(bucket.bucket).toISOString().slice(0, 13),
      bucket,
    ]),
  );
  const hours = data.series.map((point) =>
    new Date(point.hour).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  );
  const stats = [
    { label: 'Healthy tenants', value: `${k.healthy} / ${tenants.data!.total}`, icon: Users },
    {
      label: 'Success rate',
      value: <NumberValue value={k.success_rate} suffix="%" />,
      icon: CheckCheck,
    },
    { label: 'Failed runs', value: k.failed_runs, icon: ShieldCheck },
    {
      label: 'CDC duration',
      value: <NumberValue value={k.cdc_avg_min} suffix=" min" />,
      icon: Clock3,
    },
    {
      label: 'SLA compliance',
      value: <NumberValue value={k.sla_compliance} suffix="%" />,
      icon: TrendingUp,
    },
    { label: 'Running now', value: k.running_now, icon: Activity },
  ];

  return (
    <>
      <PageHeader
        title="Metrics overview"
        description="Workspace health and pipeline performance. This account has read-only metrics access."
        eyebrow="METRICS · READ ONLY"
        actions={
          <span className="updated-label">
            Updated <Time value={data.as_of} relative />
          </span>
        }
      />
      <div className="kpi-grid executive-metrics metrics-only-kpis">
        {stats.map((stat) => (
          <div className="kpi-card" key={stat.label}>
            <div className="kpi-label">
              {stat.label}
              <stat.icon size={15} />
            </div>
            <div className="kpi-value">{stat.value}</div>
            {stat.label === 'Failed runs' && (
              <div className="kpi-foot">{k.total_runs.toLocaleString()} total runs in range</div>
            )}
          </div>
        ))}
      </div>
      <div className="two-column charts-row">
        <Panel
          title="Run activity"
          subtitle={
            tenant
              ? `Aggregate passed, failed and active runs for ${tenant.display_name}`
              : 'Aggregate pipeline runs by hour'
          }
          action={
            <Select
              aria-label="Metrics tenant"
              value={selectedTenant}
              onChange={(event) => set('activity_tenant', event.target.value)}
            >
              <option value="">All tenants</option>
              {tenantItems.map((item) => (
                <option key={item.tenant_id} value={item.tenant_id}>
                  {item.display_name}
                </option>
              ))}
            </Select>
          }
        >
          <Chart
            label="Aggregate runs per hour by status"
            option={{
              legend: { top: 0, right: 20, textStyle: { color: cssColor('--run'), fontSize: 10 } },
              xAxis: {
                type: 'category',
                boundaryGap: false,
                data: hours,
                axisLine: { show: false },
                axisTick: { show: false },
                axisLabel: {
                  color: cssColor('--run'),
                  fontSize: 10,
                  interval: Math.max(0, Math.floor(hours.length / 8)),
                },
              },
              yAxis: {
                type: 'value',
                splitLine: { lineStyle: { color: cssColor('--run', 0.1059), type: 'dashed' } },
              },
              series: ['success', 'failed', 'running'].map((status) => ({
                name: status === 'success' ? 'Passed' : status[0].toUpperCase() + status.slice(1),
                type: 'line',
                smooth: 0.35,
                symbol: 'circle',
                symbolSize: 5,
                lineStyle: { width: 2 },
                showSymbol: false,
                areaStyle: { opacity: 0.06 },
                itemStyle: { color: STATUS_COLORS[status] },
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
        </Panel>
        <Panel title="Duration by pipeline" subtitle="Average and p95 of successful runs">
          <div className="duration-summary">
            {data.durations.map((duration) => (
              <div className="duration-row" key={duration.name}>
                <span>{duration.name.replace('mysql', 'MySQL').replace('mongo', 'Mongo')}</span>
                <div className="duration-track">
                  <i
                    style={{
                      width: `${Math.min(100, ((duration.avg_min || 0) / Math.max(...data.durations.map((item) => item.p95_min || 1))) * 100)}%`,
                    }}
                  />
                </div>
                <strong>
                  <NumberValue value={duration.avg_min} suffix="m" />
                  <small>
                    p95 <NumberValue value={duration.p95_min} suffix="m" />
                  </small>
                </strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <Panel title="Tenant health metrics" subtitle="Aggregate health, freshness and SLA measures">
        {tenantItems.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Tenant</th>
                  <th>Health</th>
                  <th>Failed · 24h</th>
                  <th>Freshness</th>
                  <th>SLA compliance</th>
                  <th>Last successful run</th>
                </tr>
              </thead>
              <tbody>
                {tenantItems.map((item) => (
                  <tr key={item.tenant_id}>
                    <td>
                      <strong>{item.display_name}</strong>
                      <small className="muted block">{item.tenant_id}</small>
                    </td>
                    <td>
                      <StatusPill status={item.health} />
                    </td>
                    <td>{item.failures_24h}</td>
                    <td>
                      {item.worst_stale_min == null ? '—' : `${Math.round(item.worst_stale_min)}m`}
                      <small className="muted"> / {item.freshness_sla_min}m SLA</small>
                    </td>
                    <td>
                      <NumberValue value={item.sla_compliance} suffix="%" />
                    </td>
                    <td>
                      <Time value={item.last_success_at} relative />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No tenant metrics yet">
            Metrics will appear when tenants are registered.
          </Empty>
        )}
      </Panel>
    </>
  );
}
