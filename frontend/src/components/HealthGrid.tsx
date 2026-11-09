import { ArrowUpRight, Check, Circle, LoaderCircle, X } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Schema } from '../api/client';
import { runPath } from '../api/client';
import { StatusPill } from './StatusPill';
import { STATUS_COLORS } from './statusColors';
import { Time } from './ui';

export function HealthGrid({ tenants }: { tenants: Schema<'Tenant'>[] }) {
  return (
    <div className="table-scroll">
      <table className="health-table">
        <thead>
          <tr>
            <th>Tenant</th>
            <th>Health</th>
            <th>MySQL CDC</th>
            <th>MySQL initial</th>
            <th>Mongo CDC</th>
            <th>Mongo initial</th>
            <th>Data freshness</th>
            <th>Last success</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {tenants.map((tenant) => (
            <tr key={tenant.tenant_id} className={`health-row health-${tenant.health}`}>
              <td>
                <Link className="tenant-name" to={`/tenants/${tenant.tenant_id}`}>
                  <span className={`tenant-avatar avatar-${tenant.health}`}>
                    {tenant.display_name
                      .split(' ')
                      .map((v) => v[0])
                      .join('')
                      .slice(0, 2)}
                  </span>
                  <span>
                    <strong>{tenant.display_name}</strong>
                    <small>{tenant.tenant_id}</small>
                  </span>
                </Link>
              </td>
              <td>
                <StatusPill status={tenant.health} />
              </td>
              {(['mysql:cdc', 'mysql:initial', 'mongo:cdc', 'mongo:initial'] as const).map(
                (pipeline) => {
                  const [source, load] = pipeline.split(':');
                  const run = tenant.latest_runs?.find(
                    (r) => r.source_type === source && r.load_type === load,
                  );
                  return (
                    <td key={pipeline}>
                      {run ? (
                        <Link
                          to={runPath(run.run_key)}
                          className={`pipeline-cell pipeline-${run.status}`}
                          aria-label={`${tenant.display_name} ${source} ${load}: ${run.status}`}
                          title={`${source} ${load}: ${run.status}`}
                          style={{ color: STATUS_COLORS[run.status] }}
                        >
                          {run.status === 'success' ? (
                            <Check size={14} />
                          ) : run.status === 'failed' ? (
                            <X size={14} />
                          ) : run.status === 'running' ? (
                            <LoaderCircle size={14} className="spin" />
                          ) : (
                            <Circle size={12} />
                          )}
                          <span>
                            {run.status === 'success'
                              ? 'Passed'
                              : run.status[0].toUpperCase() + run.status.slice(1)}
                          </span>
                        </Link>
                      ) : (
                        <span className="muted">Not started</span>
                      )}
                    </td>
                  );
                },
              )}
              <td>
                <div className="freshness-cell">
                  <span
                    className={
                      tenant.worst_stale_min != null &&
                      tenant.worst_stale_min > tenant.freshness_sla_min
                        ? 'danger-text'
                        : ''
                    }
                  >
                    {tenant.worst_stale_min == null
                      ? 'No sync yet'
                      : `${Math.round(tenant.worst_stale_min)}m`}
                    <small> / {tenant.freshness_sla_min}m SLA</small>
                  </span>
                  <div className="mini-track">
                    <i
                      style={{
                        width: `${Math.min(100, ((tenant.worst_stale_min || 0) / tenant.freshness_sla_min) * 100)}%`,
                        background: STATUS_COLORS[tenant.health],
                      }}
                    />
                  </div>
                </div>
              </td>
              <td className="muted">
                <Time value={tenant.last_success_at} relative />
              </td>
              <td>
                <Link
                  className="icon-link"
                  aria-label={`Open ${tenant.display_name}`}
                  to={`/tenants/${tenant.tenant_id}`}
                >
                  <ArrowUpRight size={16} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
