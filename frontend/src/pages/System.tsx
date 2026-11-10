import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Database, KeyRound, Plus, Search, Server, ShieldCheck, Trash2, X } from 'lucide-react';
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

const PERMISSION_LABELS: Record<string, string> = {
  view_console: 'View console',
  trigger_pipelines: 'Trigger & retry pipelines',
  manage_tenants: 'Onboard & edit tenants',
  manage_alerts: 'Acknowledge & resolve alerts',
  manage_users: 'Manage users & roles',
  manage_platform: 'Platform operations',
};

function RolesPanel({ roles }: { roles: Schema<'RoleOut'>[] }) {
  const { notify } = useApp();
  const client = useQueryClient();
  const [name, setName] = useState('');
  const [baseLevel, setBaseLevel] = useState('operator');
  const [description, setDescription] = useState('');
  const [picked, setPicked] = useState<string[]>(['trigger_pipelines']);
  const create = useMutation({
    mutationFn: () =>
      api<Schema<'RoleOut'>>('/roles', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          base_level: baseLevel,
          permissions: picked,
          description: description || null,
        }),
      }),
    onSuccess: (role) => {
      notify(`Role ${role.name} created. Assign it from the user table above.`);
      setName('');
      setDescription('');
      setPicked(['trigger_pipelines']);
      void client.invalidateQueries({ queryKey: ['roles'] });
    },
    onError: (e) => notify(e.message),
  });
  const remove = useMutation({
    mutationFn: (roleName: string) =>
      api<Schema<'Message'>>(`/roles/${encodeURIComponent(roleName)}`, { method: 'DELETE' }),
    onSuccess: (r) => {
      notify(r.message);
      void client.invalidateQueries();
    },
    onError: (e) => notify(e.message),
  });
  const toggle = (permission: string) =>
    setPicked((prev) =>
      prev.includes(permission) ? prev.filter((x) => x !== permission) : [...prev, permission],
    );
  return (
    <Panel
      title="Roles & permissions"
      subtitle="A role is a named bundle: pick who it is for, choose an access level, then tick what it can do. Assign it to people in the user table above."
    >
      <div className="roles-list">
        {roles.map((role) => (
          <div className="role-card" key={role.name}>
            <div className="role-card-head">
              <strong>{role.name}</strong>
              <span className="tag">
                {role.system ? 'BUILT-IN' : `CUSTOM · ${role.base_level.toUpperCase()} ACCESS`}
              </span>
              {!role.system && (
                <button
                  className="icon-button"
                  aria-label={`Delete role ${role.name}`}
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(role.name)}
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
            {role.description && <p className="role-desc">{role.description}</p>}
            <div className="role-perms">
              {role.permissions.map((permission) => (
                <span className="tag" key={permission}>
                  {PERMISSION_LABELS[permission] || permission}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <form
        className="role-form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <h4>
          <Plus size={15} /> Create a role
        </h4>
        <div className="role-form-grid">
          <label>
            Role name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. support_engineer"
              required
              minLength={2}
            />
          </label>
          <label>
            Access level
            <select value={baseLevel} onChange={(e) => setBaseLevel(e.target.value)}>
              <option value="viewer">Viewer — look, don’t touch</option>
              <option value="operator">Operator — run day-to-day work</option>
              <option value="admin">Admin — full control</option>
            </select>
          </label>
          <label>
            What is this role for? (optional)
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. On-call support engineers"
            />
          </label>
        </div>
        <fieldset className="role-perms-picker">
          <legend>Permissions — tick what this role can do</legend>
          {Object.entries(PERMISSION_LABELS).map(([permission, label]) => (
            <label key={permission} className="check-row">
              <input
                type="checkbox"
                checked={permission === 'view_console' || picked.includes(permission)}
                disabled={permission === 'view_console'}
                onChange={() => toggle(permission)}
              />
              {label}
              {permission === 'view_console' && <small> (always on)</small>}
            </label>
          ))}
        </fieldset>
        <button className="button primary" disabled={create.isPending || name.trim().length < 2}>
          <Plus size={14} /> Create role
        </button>
      </form>
    </Panel>
  );
}

export function Admin() {
  const { isAdmin, notify, runtime } = useApp();
  const { page, set } = useFilters();
  const client = useQueryClient();
  const users = useQuery({
    queryKey: ['users'],
    queryFn: () => api<Schema<'Page_User_'>>('/users'),
    enabled: isAdmin,
  });
  const audit = useQuery({
    queryKey: ['audit', page],
    queryFn: () => api<Schema<'Page_AuditEntry_'>>(`/audit?page=${page}`),
    enabled: isAdmin,
  });
  const [resetInfo, setResetInfo] = useState<{ temporary: string } | null>(null);
  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: () => api<Schema<'RoleOut'>[]>('/roles'),
    enabled: isAdmin,
  });
  const customRoles = (roles.data ?? []).filter((r) => !r.system);
  const reset = useMutation({
    mutationFn: (id: number) =>
      api<Schema<'PasswordResetResult'>>(`/users/${id}/reset-password`, { method: 'POST' }),
    onSuccess: (r) => setResetInfo({ temporary: r.temporary_password }),
    onError: (e) => notify(e.message),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { role?: string; role_name?: string } }) =>
      api<Schema<'Message'>>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    onSuccess: (r) => {
      notify(r.message);
      void client.invalidateQueries();
    },
    onError: (e) => notify(e.message),
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
        title="Users & roles"
        subtitle="Viewers inspect. Operators act. Administrators manage access and settings."
      >
        {users.isPending ? (
          <Loading />
        ) : users.error ? (
          <ErrorState error={users.error} />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>User</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Authentication</th>
                  <th>Password</th>
                </tr>
              </thead>
              <tbody>
                {users.data.items.map((user) => (
                  <tr key={user.user_id}>
                    <td>
                      <strong>{user.display_name}</strong>
                    </td>
                    <td>{user.email}</td>
                    <td>
                      <select
                        aria-label={`Role for ${user.email}`}
                        value={user.role_name || user.role}
                        disabled={update.isPending || runtime.auth_provider === 'oidc'}
                        onChange={(e) => {
                          const value = e.target.value;
                          update.mutate({
                            id: user.user_id,
                            body: ['viewer', 'operator', 'admin'].includes(value)
                              ? { role: value }
                              : { role_name: value },
                          });
                        }}
                      >
                        <optgroup label="Built-in roles">
                          {['viewer', 'operator', 'admin'].map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </optgroup>
                        {customRoles.length > 0 && (
                          <optgroup label="Custom roles">
                            {customRoles.map((role) => (
                              <option key={role.name} value={role.name}>
                                {role.name} ({role.base_level})
                              </option>
                            ))}
                          </optgroup>
                        )}
                      </select>
                    </td>
                    <td>
                      <span className="tag">
                        {runtime.auth_provider === 'oidc' ? 'ORGANIZATION SSO' : 'LOCAL · ARGON2'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="button small"
                        disabled={reset.isPending || runtime.auth_provider === 'oidc'}
                        onClick={() => reset.mutate(user.user_id)}
                      >
                        <KeyRound size={13} /> Reset
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {roles.data && <RolesPanel roles={roles.data} />}
      <Operations />
      {resetInfo && (
        <div className="modal-scrim" role="presentation" onClick={() => setResetInfo(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Temporary password"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3>Temporary password</h3>
              <button className="icon-button" aria-label="Close" onClick={() => setResetInfo(null)}>
                <X size={16} />
              </button>
            </div>
            <p>
              Share this with the user once — it is not stored anywhere you can see it again. They
              sign in with it, then change it from their profile menu.
            </p>
            <p className="temp-password mono">{resetInfo.temporary}</p>
            <div className="modal-actions">
              <button className="button primary" onClick={() => setResetInfo(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
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
