import { useState } from 'react';
import { Select } from '../components/Select';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Database, KeyRound, Plus, Search, Server, ShieldCheck, Trash2, X } from 'lucide-react';
import { Operations } from './Operations';
import { Activity } from '../components/Investigation';
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
            <Select value={baseLevel} onChange={(e) => setBaseLevel(e.target.value)}>
              <option value="viewer">Viewer — look, don’t touch</option>
              <option value="operator">Operator — run day-to-day work</option>
              <option value="admin">Admin — full control</option>
            </Select>
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

const ROLE_RANK: Record<string, number> = { viewer: 0, operator: 1, admin: 2 };

function PermissionsDialog({
  target,
  onClose,
}: {
  target: { id: number; email: string };
  onClose: () => void;
}) {
  const { notify } = useApp();
  const client = useQueryClient();
  const view = useQuery({
    queryKey: ['user-permissions', target.id],
    queryFn: () => api<Schema<'UserPermissionsOut'>>(`/users/${target.id}/permissions`),
  });
  const [desired, setDesired] = useState<Set<string> | null>(null);
  const data = view.data;
  const current = desired ?? new Set(data?.effective ?? []);
  const save = useMutation({
    mutationFn: (body: Schema<'UserPermissionsIn'>) =>
      api<Schema<'UserPermissionsOut'>>(`/users/${target.id}/permissions`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      notify('Permissions updated.');
      void client.invalidateQueries({ queryKey: ['users'] });
      onClose();
    },
    onError: (e) => notify(e.message),
  });
  const toggle = (permission: string) =>
    setDesired((prev) => {
      const next = new Set(prev ?? data?.effective ?? []);
      if (next.has(permission)) next.delete(permission);
      else next.add(permission);
      return next;
    });
  const submit = () => {
    if (!data) return;
    const bundle = new Set(data.bundle);
    save.mutate({
      grants: [...current].filter((p) => !bundle.has(p)),
      revokes: data.bundle.filter((p) => !current.has(p)),
    });
  };
  return (
    <div className="modal-scrim" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="User permissions"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3>Permissions</h3>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        {view.isPending ? (
          <Loading />
        ) : view.error ? (
          <ErrorState error={view.error} />
        ) : (
          data && (
            <>
              <p>
                {target.email} — role: {data.role}
                {data.role_name ? ` (${data.role_name})` : ''}. Tick what this one user can do;
                changes apply on top of their role and to nobody else.
              </p>
              <div className="role-perms-picker">
                {data.permissions.map((meta) => {
                  const locked = (ROLE_RANK[meta.min_role] ?? 0) > (ROLE_RANK[data.role] ?? 0);
                  const inBundle = data.bundle.includes(meta.name);
                  const checked = current.has(meta.name);
                  const tag = locked
                    ? `Needs ${meta.min_role} role`
                    : meta.name === 'view_console'
                      ? 'Always on'
                      : checked && !inBundle
                        ? 'Added for this user'
                        : !checked && inBundle
                          ? 'Removed for this user'
                          : inBundle
                            ? 'From role'
                            : '';
                  return (
                    <label key={meta.name} className="check-row">
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={locked || meta.name === 'view_console' || save.isPending || !data}
                        onChange={() => toggle(meta.name)}
                      />
                      <span>{PERMISSION_LABELS[meta.name] || meta.name}</span>
                      {tag && <span className="tag">{tag}</span>}
                    </label>
                  );
                })}
              </div>
              <div className="modal-actions">
                <button className="button" onClick={onClose}>
                  Cancel
                </button>
                <button className="button primary" disabled={save.isPending} onClick={submit}>
                  {save.isPending ? 'Saving…' : 'Save permissions'}
                </button>
              </div>
            </>
          )
        )}
      </div>
    </div>
  );
}

export function Admin() {
  const { isAdmin, notify, runtime, user: currentUser } = useApp();
  const { page, set, params } = useFilters();
  const section = ['users', 'roles', 'operations', 'activity', 'audit'].includes(
    params.get('section') || '',
  )
    ? params.get('section')!
    : 'users';
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
  const [permTarget, setPermTarget] = useState<{ id: number; email: string } | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const createUser = useMutation({
    mutationFn: (body: Schema<'UserCreate'>) =>
      api<Schema<'UserCreateResult'>>('/users', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: (r) => {
      notify(r.message);
      setAddOpen(false);
      if (r.temporary_password) setResetInfo({ temporary: r.temporary_password });
      void client.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e) => notify(e.message),
  });
  const [removeTarget, setRemoveTarget] = useState<{ id: number; email: string } | null>(null);
  const removeUser = useMutation({
    mutationFn: (id: number) => api<Schema<'Message'>>(`/users/${id}`, { method: 'DELETE' }),
    onSuccess: (r) => {
      notify(r.message);
      setRemoveTarget(null);
      void client.invalidateQueries({ queryKey: ['users'] });
    },
    onError: (e) => notify(e.message),
  });
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
      <div className="admin-intro">
        <div>
          <strong>Workspace controls</strong>
          <span>Manage identities, permissions, operational outcomes, and audit records.</span>
        </div>
        <Link to="/access" className="button">
          View access policy
        </Link>
      </div>
      <nav className="admin-tabs" aria-label="Administration sections">
        {[
          ['users', 'Users'],
          ['roles', 'Roles'],
          ['operations', 'Operations'],
          ['activity', 'Activity'],
          ['audit', 'Audit trail'],
        ].map(([id, label]) => (
          <button
            type="button"
            key={id}
            aria-current={section === id ? 'page' : undefined}
            onClick={() => set('section', id)}
          >
            {label}
          </button>
        ))}
      </nav>
      {section === 'users' && (
        <Panel
          title="Users & roles"
          subtitle="Viewers inspect. Operators act. Administrators manage access and settings."
          action={
            <button
              className="button small primary"
              disabled={runtime.auth_provider === 'oidc'}
              onClick={() => setAddOpen(!addOpen)}
            >
              <Plus size={13} /> Add user
            </button>
          }
        >
          {addOpen && (
            <form
              className="settings-form"
              onSubmit={(e) => {
                e.preventDefault();
                const data = new FormData(e.currentTarget);
                const roleValue = String(data.get('role'));
                const chosen = String(data.get('initial_password') || '').trim();
                const builtin = ['viewer', 'operator', 'admin'].includes(roleValue);
                createUser.mutate({
                  email: String(data.get('email')),
                  display_name: String(data.get('display_name')),
                  role: (builtin ? roleValue : 'viewer') as 'viewer' | 'operator' | 'admin',
                  ...(builtin ? {} : { role_name: roleValue }),
                  ...(chosen ? { initial_password: chosen } : {}),
                });
              }}
            >
              <label>
                Email
                <input type="email" name="email" required placeholder="person@company.example" />
              </label>
              <label>
                Display name
                <input name="display_name" required placeholder="Full name" />
              </label>
              <label>
                Role
                <Select name="role" defaultValue="viewer">
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
                </Select>
              </label>
              <label>
                Password (optional)
                <input
                  name="initial_password"
                  minLength={8}
                  placeholder="Leave blank to generate one"
                />
              </label>
              <button className="button primary" disabled={createUser.isPending}>
                <Plus size={14} /> Create user
              </button>
            </form>
          )}
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
                    <th>Permissions</th>
                    <th>Manage</th>
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
                        <Select
                          aria-label={`Role for ${user.email}`}
                          value={user.role_name || user.role}
                          disabled={update.isPending || runtime.auth_provider === 'oidc'}
                          onChange={(e) => {
                            const value = e.target.value;
                            if (!window.confirm(`Change ${user.email}'s role to ${value}?`)) return;
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
                        </Select>
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
                          onClick={() => {
                            if (
                              window.confirm(
                                `Reset the password for ${user.email}? Existing sessions will be revoked.`,
                              )
                            )
                              reset.mutate(user.user_id);
                          }}
                        >
                          <KeyRound size={13} /> Reset
                        </button>
                      </td>
                      <td>
                        <button
                          className="button small"
                          disabled={
                            user.user_id === currentUser.user_id || runtime.auth_provider === 'oidc'
                          }
                          title={
                            user.user_id === currentUser.user_id
                              ? 'You cannot change your own permissions'
                              : `Permissions for ${user.email}`
                          }
                          onClick={() => setPermTarget({ id: user.user_id, email: user.email })}
                        >
                          <ShieldCheck size={13} /> Permissions
                        </button>
                      </td>
                      <td>
                        <button
                          className="button small"
                          disabled={
                            removeUser.isPending ||
                            user.user_id === currentUser.user_id ||
                            runtime.auth_provider === 'oidc'
                          }
                          title={
                            user.user_id === currentUser.user_id
                              ? 'You cannot remove your own account'
                              : `Remove ${user.email}`
                          }
                          onClick={() => setRemoveTarget({ id: user.user_id, email: user.email })}
                        >
                          <Trash2 size={13} /> Remove
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      )}
      {section === 'roles' &&
        (roles.isPending ? (
          <Loading />
        ) : roles.error ? (
          <ErrorState error={roles.error} />
        ) : (
          roles.data && <RolesPanel roles={roles.data} />
        ))}
      {permTarget && <PermissionsDialog target={permTarget} onClose={() => setPermTarget(null)} />}
      {section === 'operations' && <Operations />}
      {section === 'activity' && <Activity embedded />}
      {removeTarget && (
        <div className="modal-scrim" role="presentation" onClick={() => setRemoveTarget(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Remove user"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-head">
              <h3>Remove user</h3>
              <button
                className="icon-button"
                aria-label="Close"
                onClick={() => setRemoveTarget(null)}
              >
                <X size={16} />
              </button>
            </div>
            <p>
              Remove <strong>{removeTarget.email}</strong>? They will no longer be able to sign in,
              and this cannot be undone.
            </p>
            <div className="modal-actions">
              <button className="button" onClick={() => setRemoveTarget(null)}>
                Cancel
              </button>
              <button
                className="button primary"
                disabled={removeUser.isPending}
                onClick={() => removeUser.mutate(removeTarget.id)}
              >
                <Trash2 size={14} /> {removeUser.isPending ? 'Removing…' : 'Remove user'}
              </button>
            </div>
          </div>
        </div>
      )}
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
              Share this with the user once. It is not stored anywhere, so you won't be able to see
              it again. They sign in with it, then change it from their profile menu.
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
      {section === 'audit' && (
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
      )}
    </>
  );
}

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
