import './tenants.css';
import { Select } from '../components/Select';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Search } from 'lucide-react';
import { api, queryString } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { HealthGrid } from '../components/HealthGrid';
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
      <Panel className={query.isPlaceholderData ? 'is-fetching' : ''}>
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
          <Select
            aria-label="Filter by health"
            value={params.get('health') || ''}
            onChange={(e) => set('health', e.target.value)}
          >
            <option value="">All health states</option>
            {['healthy', 'degraded', 'down', 'paused', 'onboarding'].map((s) => (
              <option key={s}>{s}</option>
            ))}
          </Select>
          <span className="filter-count">
            {query.data ? `${query.data.total} tenant${query.data.total === 1 ? '' : 's'}` : '…'}
          </span>
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
