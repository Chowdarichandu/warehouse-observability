import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { runPath, type Schema } from '../api/client';
import { StatusPill } from '../components/StatusPill';

const previewSize = 3;

function runTime(run: Schema<'Run'>) {
  return Date.parse(run.ended_at || run.started_at || run.collected_at);
}

function tenantEvidence(tenant: Schema<'Tenant'>) {
  const age = tenant.worst_stale_min;
  if (age != null && age > tenant.freshness_sla_min) {
    return `Data is ${Math.ceil(age).toLocaleString()} min old (SLA ${tenant.freshness_sla_min} min)`;
  }
  if (tenant.failures_24h) {
    return `${tenant.failures_24h} failed ${tenant.failures_24h === 1 ? 'run' : 'runs'} in the last 24 hours`;
  }
  if (age != null && age > tenant.freshness_sla_min * 0.75) {
    return `Near the freshness limit at ${Math.floor(age)} of ${tenant.freshness_sla_min} min`;
  }
  return '';
}

function AttentionRow({ tenant }: { tenant: Schema<'Tenant'> }) {
  // A latest failed CDC run is evidence. It may not explain the tenant's health on its own.
  const failedRun = tenant.latest_runs
    .filter((run) => run.load_type === 'cdc' && run.status === 'failed' && !run.in_maintenance)
    .sort((a, b) => runTime(b) - runTime(a))[0];
  const evidence = tenantEvidence(tenant);
  const run =
    failedRun ??
    (evidence ? undefined : tenant.latest_runs.find((item) => item.status === 'running'));
  const source = run?.source_type === 'mysql' ? 'MySQL' : 'MongoDB';
  const pipeline = `${source} ${run?.load_type === 'cdc' ? 'CDC' : 'initial load'}`;
  return (
    <li className="overview-attention-row">
      <div className="overview-attention-name">
        <Link to={`/tenants/${encodeURIComponent(tenant.tenant_id)}`}>{tenant.display_name}</Link>
        <StatusPill status={tenant.health} />
      </div>
      <div className="overview-attention-evidence">
        {run && (
          <Link
            to={runPath(run.run_key)}
            aria-label={`Inspect ${run.status} ${pipeline} run for ${tenant.display_name}`}
          >
            {pipeline} {run.status} <ArrowRight aria-hidden="true" size={14} />
          </Link>
        )}
        {evidence && <span>{evidence}</span>}
      </div>
    </li>
  );
}

export function OverviewHealth({
  tenants,
  total,
  kpis,
}: {
  tenants: Schema<'Tenant'>[];
  total: number;
  kpis: Schema<'Kpis'>;
}) {
  const { healthy, degraded, down, running_now: running } = kpis;
  const needsAttention = down + degraded;
  const attention = [
    ...tenants.filter((tenant) => tenant.health === 'down'),
    ...tenants.filter((tenant) => tenant.health === 'degraded'),
  ].slice(0, previewSize);
  const statuses = [
    { key: 'healthy', count: healthy, label: 'healthy' },
    { key: 'degraded', count: degraded, label: 'degraded' },
    { key: 'down', count: down, label: 'down' },
    { key: 'other', count: Math.max(0, total - healthy - degraded - down), label: 'other' },
  ];

  return (
    <div className="overview-health">
      <section className="overview-health-summary" aria-labelledby="overview-health-title">
        <h2 id="overview-health-title">Workspace health</h2>
        <p className="overview-health-figure">
          {total ? (
            <>
              <strong>{healthy.toLocaleString()}</strong> of {total.toLocaleString()} tenants
              healthy
            </>
          ) : (
            'No tenants registered'
          )}
        </p>
        {total > 0 && (
          <>
            <div className="overview-health-track" aria-hidden="true">
              {statuses
                .filter(({ count }) => count > 0)
                .map(({ key, count }) => (
                  <span key={key} data-health={key} style={{ flexGrow: count }} />
                ))}
            </div>
            <ul className="overview-health-counts" aria-label="Tenants by health">
              {statuses.map(({ key, count, label }) => {
                if (key === 'other' && !count) return null;
                const text = `${count.toLocaleString()} ${label}`;
                return (
                  <li key={key}>
                    <span aria-hidden="true" data-health={key} />
                    {count > 0 && key !== 'other' ? (
                      <Link to={`/tenants?health=${key}`}>{text}</Link>
                    ) : (
                      <span>{text}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
        <p className="overview-health-progress">
          {running ? (
            <Link to="/runs?status=running">
              {running.toLocaleString()} {running === 1 ? 'run' : 'runs'} in progress
            </Link>
          ) : (
            'No runs in progress'
          )}
        </p>
      </section>
      <section className="overview-attention" aria-labelledby="overview-attention-title">
        <div className="overview-attention-header">
          <h2 id="overview-attention-title">Needs attention</h2>
          <span>
            {attention.length > 0 && needsAttention > attention.length
              ? `${attention.length} of `
              : ''}
            {needsAttention.toLocaleString()} {needsAttention === 1 ? 'tenant' : 'tenants'}
          </span>
        </div>
        {attention.length ? (
          <ul className="overview-attention-list">
            {attention.map((tenant) => (
              <AttentionRow key={tenant.tenant_id} tenant={tenant} />
            ))}
          </ul>
        ) : (
          <p className="overview-attention-empty">
            {total
              ? 'No down or degraded tenants in this view.'
              : 'Tenant issues will appear here.'}
          </p>
        )}
        {needsAttention > attention.length && (
          <Link className="text-link" to="/tenants">
            Browse all tenants <ArrowRight aria-hidden="true" size={14} />
          </Link>
        )}
      </section>
    </div>
  );
}
