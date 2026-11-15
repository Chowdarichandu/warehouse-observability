import './system.css';
import { useQuery } from '@tanstack/react-query';
import { Database, Server } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { StatusPill } from '../components/StatusPill';
import { STATUS_COLORS } from '../components/statusColors';
import { Empty, ErrorState, Loading, NumberValue, PageHeader, Panel, Time } from '../components/ui';

export function Platform() {
  const query = useQuery({
    queryKey: ['platform'],
    queryFn: () => api<Schema<'Platform'>>('/platform/health'),
  });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const { components, history, collectors, database_bytes } = query.data;
  const pools = components.find((c) => c.component === 'airflow_pools');
  const imports = history.filter(
    (c) => c.component === 'airflow_import_errors' && c.status !== 'up',
  );
  return (
    <>
      <PageHeader
        title="Platform health"
        description="Airflow, Airbyte and platform checks are collected server-side; this view refreshes every 30 seconds."
        actions={
          <StatusPill
            status={components.every((c) => c.status === 'up') ? 'healthy' : 'degraded'}
          />
        }
      />
      <div className="component-grid">
        {components.map((component) => (
          <Panel key={component.component}>
            <div className="component-card">
              <Server size={18} />
              <StatusPill status={component.status} />
              <h3>{component.component.replaceAll('_', ' ')}</h3>
              <p>{String(component.details?.message || 'All checks passing')}</p>
              <small>
                Checked <Time value={component.checked_at} relative />
              </small>
            </div>
          </Panel>
        ))}
      </div>
      <Panel
        title="Component history"
        subtitle="The previous 48 hours · hover for the UTC check time"
      >
        <div className="platform-history">
          {components.map((component) => (
            <div key={component.component}>
              <strong>{component.component.replaceAll('_', ' ')}</strong>
              <div>
                {history
                  .filter((h) => h.component === component.component)
                  .map((h) => (
                    <span
                      key={`${h.checked_at}:${h.status}`}
                      style={{ background: STATUS_COLORS[h.status] }}
                      title={`${h.checked_at} UTC · ${h.status} · ${h.details?.message || ''}`}
                    />
                  ))}
              </div>
              <StatusPill status={component.status} />
            </div>
          ))}
        </div>
      </Panel>
      <div className="two-column">
        <Panel title="Airflow pool capacity">
          <div className="pool-card">
            <h3>{String(pools?.details?.pool || 'default_pool')}</h3>
            <div className="pool-number">
              {String(pools?.details?.occupied || 0)}
              <span>/ {String(pools?.details?.slots || 32)} slots occupied</span>
            </div>
            <div className="pool-track">
              <i
                style={{
                  width: `${(Number(pools?.details?.occupied || 0) / Number(pools?.details?.slots || 32)) * 100}%`,
                }}
              />
            </div>
            <p>{String(pools?.details?.queued || 0)} tasks waiting in queue</p>
          </div>
        </Panel>
        <Panel title="Observability store">
          <div className="pool-card">
            <Database size={27} />
            <div className="pool-number">
              <NumberValue value={database_bytes / 1024 / 1024} />
              <span>MB</span>
            </div>
            <p>Postgres 16 · schema obs · UTC timestamps</p>
            <span className="positive-text">Database connection healthy</span>
          </div>
        </Panel>
      </div>
      <Panel
        title="DAG import errors"
        subtitle="Historical incidents remain visible after they have been fixed."
      >
        {imports.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Incident</th>
                  <th>Status</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {imports.map((event) => (
                  <tr key={event.checked_at}>
                    <td className="mono">{String(event.details?.message)}</td>
                    <td>
                      <StatusPill status="resolved" />
                    </td>
                    <td>
                      <Time value={event.checked_at} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty title="No import errors in the observed history" />
        )}
      </Panel>
      <Panel
        title="Collector diagnostics"
        subtitle="Each source is polled independently. One failure does not stop the other collectors."
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Component</th>
                <th>Last success</th>
                <th>Poll duration</th>
                <th>Watermark</th>
                <th>Last error</th>
              </tr>
            </thead>
            <tbody>
              {collectors.map((collector) => (
                <tr key={collector.component}>
                  <td className="mono">{collector.component}</td>
                  <td>
                    <Time value={collector.last_success_at} relative />
                  </td>
                  <td>{collector.last_poll_ms ?? '—'} ms</td>
                  <td>
                    <Time value={collector.watermark} />
                  </td>
                  <td>{collector.last_error || <span className="positive-text">None</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
