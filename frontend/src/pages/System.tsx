import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Database, Search, Server, ShieldCheck } from 'lucide-react';
import { Operations } from './Operations';
import { api, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
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
  Time,
  useFilters,
} from '../components/ui';

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
        description="The systems behind your pipelines, observed independently of Airflow."
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

export function Admin() {
  const { isAdmin } = useApp();
  const { page, set } = useFilters();
  const audit = useQuery({
    queryKey: ['audit', page],
    queryFn: () => api<Schema<'Page_AuditEntry_'>>(`/audit?page=${page}`),
    enabled: isAdmin,
  });
  if (!isAdmin)
    return (
      <>
        <PageHeader title="Administration" description="Workspace access and audit history." />
        <div className="notice info">
          <ShieldCheck size={21} />
          <p>This page requires the Admin role.</p>
        </div>
      </>
    );
  return (
    <>
      <PageHeader
        title="Administration"
        description="Manage workspace access and review a complete history of actions."
      />
      <Panel
        title="Workspace governance"
        subtitle="Review operational decisions, access, and the evidence behind every change."
      >
        <div className="governance-link">
          <ShieldCheck size={21} />
          <div>
            <strong>Access & roles</strong>
            <p>Manage team permissions, identity source, and active sessions in one place.</p>
          </div>
          <Link className="button" to="/access">
            Manage access
          </Link>
        </div>
      </Panel>
      <Operations />
      <Panel
        title="Audit trail"
        subtitle="Every successful mutation records its actor, target, and timestamp."
      >
        {audit.isPending ? (
          <Loading />
        ) : audit.error ? (
          <ErrorState error={audit.error} />
        ) : audit.data.items.length ? (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>When</th>
                    <th>Actor</th>
                    <th>Action</th>
                    <th>Target</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.data.items.map((entry) => (
                    <tr key={entry.id}>
                      <td>
                        <Time value={entry.at} />
                      </td>
                      <td className="mono">{entry.actor}</td>
                      <td>
                        <span className="tag">{entry.action.replaceAll('_', ' ')}</span>
                      </td>
                      <td className="mono truncate-cell" title={entry.target || ''}>
                        {entry.target || '—'}
                      </td>
                      <td className="mono truncate-cell">{JSON.stringify(entry.details)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              total={audit.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
          </>
        ) : (
          <Empty title="No actions recorded yet" />
        )}
      </Panel>
    </>
  );
}

export function SearchResults() {
  const { params, set, page } = useFilters();
  const term = params.get('q') || '';
  const query = useQuery({
    queryKey: ['search', term, page],
    queryFn: () =>
      api<Schema<'Page_SearchHit_'>>(`/search?q=${encodeURIComponent(term)}&page=${page}`),
    enabled: term.length > 1,
  });
  return (
    <>
      <PageHeader
        title="Search your pipelines"
        description="Full-text search across classified errors and stored, redacted logs."
      />
      <Panel>
        <form
          className="filter-bar"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            set('q', String(data.get('q')));
          }}
        >
          <label className="search-field wide">
            <Search size={16} />
            <input
              name="q"
              aria-label="Search query"
              placeholder="Try binlog, replication, or schema…"
              defaultValue={term}
              minLength={2}
              required
            />
          </label>
          <button className="button primary">Search</button>
        </form>
        {term.length < 2 ? (
          <Empty title="Find a clue, follow the run">
            Enter at least two characters to search.
          </Empty>
        ) : query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data?.items.length ? (
          <>
            <div className="search-results">
              {query.data.items.map((hit) => (
                <Link to={runPath(hit.run_key)} key={hit.run_key}>
                  <div className="inline-flex">
                    <strong>{hit.tenant_id}</strong>
                    <span className="tag mono">{hit.error_class}</span>
                  </div>
                  <p>{hit.excerpt}</p>
                  <small>
                    <Time value={hit.started_at} />
                  </small>
                </Link>
              ))}
            </div>
            <Pagination
              total={query.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
          </>
        ) : (
          <Empty title={`No matches for “${term}”`} />
        )}
      </Panel>
    </>
  );
}
