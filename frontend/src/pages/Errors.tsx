import { useQuery } from '@tanstack/react-query';
import { Select } from '../components/Select';
import { ArrowRight, Layers3, Search } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { Chart } from '../components/Chart';
import { RunsTable } from '../components/RunsTable';
import {
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Pagination,
  Panel,
  TenantLink,
  Time,
  useFilters,
} from '../components/ui';

export function Errors() {
  const { params, set, rangeQuery, page } = useFilters();
  const fingerprint = params.get('group') || '';
  const query = useQuery({
    queryKey: ['errors', rangeQuery, page],
    queryFn: () => api<Schema<'Page_ErrorGroup_'>>(`/errors/groups?${rangeQuery}&page=${page}`),
  });
  const group = useQuery({
    queryKey: ['error-group', fingerprint, rangeQuery, params.get('run_page')],
    queryFn: () =>
      api<Schema<'ErrorGroupDetail'>>(
        `/errors/groups/${fingerprint}?${rangeQuery}&page=${params.get('run_page') || 1}`,
      ),
    enabled: !!fingerprint,
  });
  const heatmap = useQuery({
    queryKey: ['heatmap', rangeQuery, params.get('heat_tenant')],
    queryFn: () =>
      api<Schema<'Page_HeatCell_'>>(
        `/metrics/failures-heatmap?${rangeQuery}&tenant=${params.get('heat_tenant') || ''}`,
      ),
  });
  const mttr = useQuery({
    queryKey: ['mttr', rangeQuery],
    queryFn: () => api<Schema<'Page_Mttr_'>>(`/metrics/mttr?${rangeQuery}`),
  });
  const stages = useQuery({
    queryKey: ['failure-stages', rangeQuery],
    queryFn: () =>
      api<Schema<'Page_Breakdown_'>>(`/metrics/failures-breakdown?group_by=stage&${rangeQuery}`),
  });
  const byTenant = useQuery({
    queryKey: ['failure-tenants', rangeQuery],
    queryFn: () =>
      api<Schema<'Page_Breakdown_'>>(`/metrics/failures-breakdown?group_by=tenant&${rangeQuery}`),
  });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const groups = query.data.items;
  const total = groups.reduce((sum, g) => sum + g.occurrences, 0);
  return (
    <>
      <PageHeader
        title="Error intelligence"
        description="Failures grouped by root cause, across all tenants."
      />
      <div className="insight-banner">
        <Layers3 size={25} />
        <div>
          <strong>
            {total} failures. {query.data.total} root causes.
          </strong>
          <p>
            Similar errors are fingerprinted and grouped automatically. Secrets are redacted before
            storage.
          </p>
        </div>
        <span className="tag">AUTOMATIC CLASSIFICATION</span>
      </div>
      <Panel title="Error groups" subtitle="Recurring failures with a shared root cause">
        {groups.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Error class & sample</th>
                  <th>Occurrences</th>
                  <th>Tenants</th>
                  <th>First / last seen</th>
                  <th>Daily trend</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {groups.map((g) => (
                  <tr
                    key={g.fingerprint}
                    className={fingerprint === g.fingerprint ? 'selected-row' : ''}
                  >
                    <td>
                      <button
                        className="group-button"
                        onClick={() =>
                          set('group', fingerprint === g.fingerprint ? '' : g.fingerprint)
                        }
                      >
                        <strong>{g.error_class}</strong>
                        <span>{g.sample_message}</span>
                      </button>
                    </td>
                    <td>
                      <span className="count-pill">{g.occurrences}</span>
                    </td>
                    <td>
                      <span className="mono">{g.tenants.length} tenants</span>
                    </td>
                    <td>
                      <Time value={g.first_seen} />
                      <small className="block muted">
                        <Time value={g.last_seen} relative />
                      </small>
                    </td>
                    <td>
                      <div className="sparkline">
                        {g.trend?.map((n, index) => (
                          <i
                            key={index}
                            style={{ height: `${Math.max(3, (n / Math.max(...g.trend!)) * 30)}px` }}
                          />
                        ))}
                      </div>
                    </td>
                    <td>
                      <button
                        className="icon-button"
                        aria-label={`Inspect ${g.error_class}`}
                        onClick={() => set('group', g.fingerprint)}
                      >
                        <ArrowRight size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No errors in this range" />
        )}
        <Pagination total={query.data.total} page={page} onChange={(p) => set('page', String(p))} />
      </Panel>
      {fingerprint && (
        <Panel
          title={group.data?.group.error_class || 'Group investigation'}
          action={
            <button className="text-button" onClick={() => set('group', '')}>
              Close
            </button>
          }
        >
          {group.isPending ? (
            <Loading />
          ) : group.error ? (
            <ErrorState error={group.error} />
          ) : (
            group.data && (
              <>
                <div className="group-description">
                  <p>{group.data.group.sample_message}</p>
                  <div className="inline-flex">
                    {group.data.group.tenants.map((id) => (
                      <TenantLink id={id} key={id} />
                    ))}
                  </div>
                  <p className="muted">
                    These failures come from Airflow task runs. Open a run's Airflow log to see the
                    exact task error; a failed run can be retried from its run page.
                  </p>
                </div>
                <RunsTable runs={group.data.runs.items} logLink />
                <Pagination
                  total={group.data.runs.total}
                  page={Number(params.get('run_page') || 1)}
                  onChange={(p) => set('run_page', String(p))}
                />
              </>
            )
          )}
        </Panel>
      )}
      <div className="two-column">
        <Panel
          title="Failure patterns"
          subtitle="Failures by hour and weekday · UTC"
          action={
            <Select
              aria-label="Heatmap tenant"
              value={params.get('heat_tenant') || ''}
              onChange={(e) => set('heat_tenant', e.target.value)}
            >
              <option value="">All tenants</option>
              <option value="cedar_foods">Cedar Foods</option>
              <option value="acme_retail">Acme Retail</option>
            </Select>
          }
        >
          {heatmap.isPending ? (
            <Loading />
          ) : heatmap.error ? (
            <ErrorState error={heatmap.error} />
          ) : (
            <Chart
              label="Failure heatmap by hour and weekday"
              height={290}
              option={{
                tooltip: {
                  formatter: (value: unknown) => {
                    const v = value as { value: number[] };
                    return `${v.value[0]}:00 UTC · ${v.value[2]} failures`;
                  },
                },
                grid: { left: 52, top: 15, right: 20, bottom: 55 },
                xAxis: {
                  type: 'category',
                  data: Array.from({ length: 24 }, (_, i) => `${i}`),
                  splitArea: { show: true },
                  axisLabel: { color: '#81909f', fontSize: 10 },
                },
                yAxis: {
                  type: 'category',
                  data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
                  axisLabel: { color: '#81909f' },
                },
                visualMap: {
                  min: 0,
                  max: Math.max(5, ...heatmap.data.items.map((v) => v.failures)),
                  orient: 'horizontal',
                  left: 'center',
                  bottom: 0,
                  itemHeight: 100,
                  itemWidth: 8,
                  text: ['More', 'Less'],
                  textStyle: { color: '#81909f' },
                  inRange: { color: ['#eaf2ee', '#a4c9b5', '#e3ad76', '#d45e5f'] },
                },
                series: [
                  {
                    type: 'heatmap',
                    data: Array.from({ length: 7 * 24 }, (_, i) => {
                      const day = Math.floor(i / 24);
                      const hour = i % 24;
                      return [
                        hour,
                        day,
                        heatmap.data.items.find((c) => c.weekday === day && c.hour === hour)
                          ?.failures || 0,
                      ];
                    }),
                    itemStyle: { borderColor: '#ffffff55', borderWidth: 2, borderRadius: 3 },
                  },
                ],
              }}
            />
          )}
        </Panel>
        <Panel
          title="Mean time to recovery"
          subtitle="Failure → next success, for the same tenant and pipeline"
        >
          {mttr.isPending ? (
            <Loading />
          ) : mttr.error ? (
            <ErrorState error={mttr.error} />
          ) : mttr.data.items.length ? (
            <div className="mttr-list">
              {mttr.data.items.map((row) => (
                <div key={row.tenant_id}>
                  <TenantLink id={row.tenant_id} />
                  <div className="mttr-track">
                    <i
                      style={{
                        width: `${Math.max(2, ((row.avg_min || 0) / Math.max(...mttr.data.items.map((m) => m.avg_min || 1))) * 100)}%`,
                      }}
                    />
                  </div>
                  <strong>
                    <NumberValue value={row.avg_min} suffix="m" />
                    <small>
                      {row.recovered} recovered · {row.unresolved} open
                    </small>
                  </strong>
                </div>
              ))}
            </div>
          ) : (
            <Empty title="No failures to measure" />
          )}
        </Panel>
      </div>
      <div className="two-column">
        {[
          { title: 'Failures by stage', query: stages },
          { title: 'Failures by tenant', query: byTenant },
        ].map(({ title, query: breakdown }) => (
          <Panel key={title} title={title}>
            {breakdown.isPending ? (
              <Loading />
            ) : breakdown.error ? (
              <ErrorState error={breakdown.error} />
            ) : (
              <Chart
                label={title}
                height={280}
                option={{
                  grid: { left: 120, right: 25, top: 15, bottom: 30 },
                  xAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
                  yAxis: {
                    type: 'category',
                    data: breakdown.data.items.map((row) => row.name),
                    axisLabel: { color: '#81909f', fontSize: 9 },
                  },
                  series: [
                    {
                      type: 'bar',
                      barMaxWidth: 18,
                      itemStyle: { color: '#9cb7c6', borderRadius: [0, 3, 3, 0] },
                      data: breakdown.data.items.map((row) => row.count),
                    },
                  ],
                }}
              />
            )}
          </Panel>
        ))}
      </div>
      <Panel
        title="Failures by class"
        subtitle="Occurrence counts in the selected range"
        action={
          <span className="chart-label">
            <Search size={13} /> ROOT CAUSES
          </span>
        }
      >
        <Chart
          label="Failure count by error class"
          height={260}
          option={{
            grid: { left: 210, right: 35, top: 10, bottom: 30 },
            yAxis: {
              type: 'category',
              data: groups.map((g) => g.error_class),
              axisLabel: { color: '#81909f', fontSize: 10 },
            },
            xAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
            series: [
              {
                type: 'bar',
                data: groups.map((g) => g.occurrences),
                barMaxWidth: 18,
                itemStyle: { color: '#d66c6b', borderRadius: [0, 3, 3, 0] },
              },
            ],
          }}
        />
      </Panel>
    </>
  );
}
