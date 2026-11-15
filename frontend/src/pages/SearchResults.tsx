import './system.css';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { api, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { StatusPill } from '../components/StatusPill';
import {
  Empty,
  ErrorState,
  Loading,
  PageHeader,
  Pagination,
  Panel,
  Time,
  useFilters,
} from '../components/ui';

const SEARCH_PAGES = [
  { label: 'Overview', path: '/', keywords: 'health dashboard' },
  { label: 'Tenants', path: '/tenants', keywords: 'customers sources' },
  { label: 'Pipeline orchestration', path: '/pipelines', keywords: 'dag workflow pipelines' },
  { label: 'Pipeline runs', path: '/runs', keywords: 'logs jobs execution' },
  { label: 'Errors', path: '/errors', keywords: 'failures investigation' },
  { label: 'Alerts', path: '/alerts', keywords: 'notifications incidents' },
  { label: 'Data quality', path: '/quality', keywords: 'checks validation' },
  { label: 'Warehouse', path: '/warehouse', keywords: 'database tables' },
  { label: 'Access & roles', path: '/access', keywords: 'permissions security' },
  { label: 'Account settings', path: '/account', keywords: 'profile password' },
  { label: 'Administration', path: '/admin', keywords: 'users roles settings', admin: true },
];

export function SearchResults() {
  const { params, set, page } = useFilters();
  const { isAdmin } = useApp();
  const term = (params.get('q') || '').trim();
  const enabled = term.length >= 2;
  const query = useQuery({
    queryKey: ['search', term, page],
    queryFn: () =>
      api<Schema<'Page_SearchHit_'>>(`/search?q=${encodeURIComponent(term)}&page=${page}`),
    enabled,
    placeholderData: () => undefined,
  });
  const tenants = useQuery({
    queryKey: ['search-tenants', term],
    queryFn: () =>
      api<Schema<'Page_Tenant_'>>(`/tenants?q=${encodeURIComponent(term)}&page_size=10`),
    enabled,
    placeholderData: () => undefined,
  });
  const pages = enabled
    ? SEARCH_PAGES.filter(
        (item) =>
          (!item.admin || isAdmin) &&
          `${item.label} ${item.keywords}`.toLowerCase().includes(term.toLowerCase()),
      )
    : [];
  return (
    <>
      <PageHeader
        title="Search"
        description="Find tenants, console pages, and evidence in pipeline logs."
      />
      <Panel className="search-panel">
        <form
          className="filter-bar search-form"
          onSubmit={(event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            set('q', String(data.get('q')).trim());
          }}
        >
          <label className="search-field wide">
            <Search size={17} />
            <input
              key={term}
              name="q"
              aria-label="Search query"
              placeholder="Search tenants, logs, or pages"
              defaultValue={term}
              maxLength={200}
              required
            />
          </label>
          <button className="button primary">Search</button>
        </form>
        {!enabled ? (
          <Empty title="Search your workspace">
            Enter at least two characters to find tenants, pages, errors, and logs.
          </Empty>
        ) : (
          <div className="search-sections">
            {pages.length > 0 && (
              <section className="search-section">
                <h2>
                  Pages <span>{pages.length}</span>
                </h2>
                <div className="search-shortcuts">
                  {pages.map((item) => (
                    <Link key={item.path} to={item.path}>
                      {item.label}
                      <span aria-hidden="true">↗</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}
            <section className="search-section">
              <h2>Tenants {tenants.data && <span>{tenants.data.total}</span>}</h2>
              {tenants.isPending ? (
                <Loading />
              ) : tenants.error ? (
                <ErrorState error={tenants.error} />
              ) : tenants.data?.items.length ? (
                <div className="tenant-search-results">
                  {tenants.data.items.map((tenant) => (
                    <Link
                      key={tenant.tenant_id}
                      to={`/tenants/${encodeURIComponent(tenant.tenant_id)}`}
                    >
                      <div className="inline-flex">
                        <strong>{tenant.display_name}</strong>
                        <StatusPill status={tenant.health} />
                      </div>
                      <small>{tenant.tenant_id}</small>
                    </Link>
                  ))}
                  {tenants.data.total > tenants.data.items.length && (
                    <Link to={`/tenants?q=${encodeURIComponent(term)}`}>
                      View all {tenants.data.total} matching tenants →
                    </Link>
                  )}
                </div>
              ) : (
                <p className="search-empty">No matching tenants.</p>
              )}
            </section>
            <section className="search-section">
              <h2>Errors & logs {query.data && <span>{query.data.total}</span>}</h2>
              <p className="search-hint">
                Searches words in classified errors and redacted run logs.
              </p>
              {query.isPending ? (
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
                          {hit.error_class && <span className="tag mono">{hit.error_class}</span>}
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
                <p className="search-empty">No matching errors or logs. Try a different word.</p>
              )}
            </section>
          </div>
        )}
      </Panel>
    </>
  );
}
