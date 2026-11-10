import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, KeyRound, LockKeyhole, LogOut, Minus, ShieldCheck, UserRound } from 'lucide-react';
import { api } from '../api/client';
import { Link } from 'react-router-dom';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import {
  Empty,
  ErrorState,
  Loading,
  PageHeader,
  Pagination,
  Panel,
  useFilters,
} from '../components/ui';
import './access.css';

export function Access() {
  const { user, notify } = useApp();
  const { params, set, page } = useFilters();
  const [confirmation, setConfirmation] = useState<number | null>(null);
  const [roleChange, setRoleChange] = useState<{
    id: number;
    role: NonNullable<Schema<'UserPatch'>['role']>;
  } | null>(null);
  const client = useQueryClient();
  const access = useQuery({
    queryKey: ['access'],
    queryFn: () => api<Schema<'AccessContext'>>('/access'),
  });
  const canRevoke = access.data?.capabilities.includes('access.revoke_sessions') || false;
  const canAssign = access.data?.capabilities.includes('access.assign_roles') || false;
  const users = useQuery({
    queryKey: ['users', page],
    queryFn: () => api<Schema<'Page_User_'>>(`/users?page=${page}`),
    enabled: canRevoke || canAssign,
  });
  const assign = useMutation({
    mutationFn: ({ id, role }: { id: number; role: NonNullable<Schema<'UserPatch'>['role']> }) =>
      api<Schema<'Message'>>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify({ role }) }),
    onSuccess: (result) => {
      setRoleChange(null);
      notify(result.message);
      for (const key of ['users', 'me', 'access', 'audit'])
        void client.invalidateQueries({ queryKey: [key] });
    },
    onError: (error) => notify(error.message),
  });
  const revoke = useMutation({
    mutationFn: (id: number) =>
      api<Schema<'Message'>>(`/users/${id}/revoke-sessions`, { method: 'POST' }),
    onSuccess: (result) => {
      setConfirmation(null);
      notify(result.message);
      void client.invalidateQueries({ queryKey: ['audit'] });
    },
    onError: (error) => notify(error.message),
  });
  if (access.isPending) return <Loading />;
  if (access.error) return <ErrorState error={access.error} />;
  const policy = access.data;
  const ownRole = policy.roles.find((role) => role.role === policy.role);
  const adminPrivileges = policy.permissions.filter(
    (permission) => permission.minimum_role === 'admin',
  );
  const isAdmin = policy.role === 'admin';
  const onlyAvailable = params.get('view') === 'available';
  const permissions = onlyAvailable
    ? policy.permissions.filter((permission) => permission.enabled)
    : policy.permissions;
  return (
    <div className="access-page">
      <PageHeader
        title="Workspace access"
        description="Understand your permissions and how access is managed."
        actions={
          <>
            {(canRevoke || canAssign) && (
              <a className="button small" href="#access-users">
                Manage user access
              </a>
            )}
            <span className="tag">
              <ShieldCheck size={14} />
              {ownRole?.label}
            </span>
          </>
        }
      />
      <div className="access-identity-grid">
        <Panel>
          <div className="access-identity">
            <span className="access-identity-icon">
              <UserRound size={23} />
            </span>
            <div>
              <span className="access-eyebrow">SIGNED IN AS</span>
              <h2>{policy.identity.display_name}</h2>
              <p>{policy.identity.email}</p>
            </div>
          </div>
          <div className="access-role-summary">
            <strong>{ownRole?.label}</strong>
            <p>{ownRole?.description}</p>
          </div>
        </Panel>
        <Panel>
          <div className="access-identity">
            <span className="access-identity-icon">
              <KeyRound size={23} />
            </span>
            <div>
              <span className="access-eyebrow">ACCESS AUTHORITY</span>
              <h2>{policy.role_assignment_managed ? 'Organization SSO' : 'Workspace roles'}</h2>
              <p>
                {policy.role_assignment_managed
                  ? 'Roles follow your configured identity-provider groups.'
                  : 'Roles are assigned by workspace administrators.'}
              </p>
            </div>
          </div>
          <p className="access-policy-note">
            {policy.role_assignment_managed
              ? 'Update group membership through your organization’s access service. Changes apply when you next sign in; an administrator can revoke existing sessions.'
              : 'Your current role is checked by the server for every action. Local passwords are available in demo mode.'}
          </p>
        </Panel>
      </div>
      {isAdmin && (
        <Panel
          title="Privilege access"
          subtitle="Admin-only controls. Every action is checked by the server and written to the audit history."
        >
          <div className="access-permissions">
            {adminPrivileges.map((permission) => (
              <div className="access-permission" key={permission.id}>
                <span className={`access-permission-icon ${permission.enabled ? 'available' : ''}`}>
                  {permission.enabled ? <Check size={17} /> : <LockKeyhole size={16} />}
                </span>
                <div>
                  <strong>{permission.label}</strong>
                  <p>{permission.description}</p>
                  {permission.reason && <small>{permission.reason}</small>}
                </div>
                <span className={`access-state ${permission.enabled ? 'available' : ''}`}>
                  {permission.enabled ? 'Available' : 'Environment restricted'}
                </span>
              </div>
            ))}
          </div>
          <div className="access-quicklinks">
            <Link className="button small" to="/admin?section=users">
              Manage users
            </Link>
            <Link className="button small" to="/admin?section=roles">
              Roles &amp; permissions
            </Link>
            <Link className="button small" to="/admin?section=operations">
              Operations
            </Link>
            <Link className="button small" to="/admin?section=audit">
              Audit history
            </Link>
            {(canRevoke || canAssign) && (
              <a className="button small" href="#access-users">
                User access &amp; sessions
              </a>
            )}
          </div>
        </Panel>
      )}
      <Panel
        title="Your permissions"
        subtitle="Role grants and environment controls determine which actions are available."
        action={
          <label className="access-filter">
            Show
            <select
              aria-label="Permission view"
              value={onlyAvailable ? 'available' : 'all'}
              onChange={(event) =>
                set('view', event.target.value === 'all' ? '' : event.target.value)
              }
            >
              <option value="all">All permissions</option>
              <option value="available">Available to me</option>
            </select>
          </label>
        }
      >
        <div className="access-permissions">
          {permissions.map((permission) => (
            <div className="access-permission" key={permission.id}>
              <span className={`access-permission-icon ${permission.enabled ? 'available' : ''}`}>
                {permission.enabled ? <Check size={17} /> : <LockKeyhole size={16} />}
              </span>
              <div>
                <strong>{permission.label}</strong>
                <p>{permission.description}</p>
                {permission.reason && <small>{permission.reason}</small>}
              </div>
              <span className={`access-state ${permission.enabled ? 'available' : ''}`}>
                {permission.enabled
                  ? 'Available'
                  : permission.allowed
                    ? 'Environment restricted'
                    : `${permission.minimum_role === 'admin' ? 'Admin' : 'Operator'} required`}
              </span>
            </div>
          ))}
        </div>
      </Panel>
      <Panel
        title="Role guide"
        subtitle="Each role includes the permissions of the roles before it. This guide does not change your access."
      >
        <div className="access-role-descriptions">
          {policy.roles.map((role) => (
            <div key={role.role} className={role.role === policy.role ? 'current' : ''}>
              <strong>
                {role.label}
                {role.role === policy.role && <span>Your role</span>}
              </strong>
              <p>{role.description}</p>
            </div>
          ))}
        </div>
        <div className="table-scroll">
          <table className="access-matrix">
            <caption className="sr-only">Workspace role permission matrix</caption>
            <thead>
              <tr>
                <th>Permission</th>
                {policy.roles.map((role) => (
                  <th key={role.role} scope="col">
                    {role.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {policy.permissions.map((permission) => (
                <tr key={permission.id}>
                  <th scope="row">{permission.label}</th>
                  {policy.roles.map((role) => (
                    <td key={role.role}>
                      {permission.roles.includes(role.role) ? (
                        <span className="access-matrix-grant">
                          <Check size={17} aria-hidden="true" />
                          <span className="sr-only">Allowed</span>
                        </span>
                      ) : (
                        <span className="access-matrix-denied">
                          <Minus size={17} aria-hidden="true" />
                          <span className="sr-only">Not allowed</span>
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="access-matrix-note">
          Live actions also require environment approval. SSO role assignments are managed by
          identity-provider groups.
        </p>
      </Panel>
      {(canRevoke || canAssign) && (
        <div id="access-users" className="access-users-section">
          <Panel
            title="User access & sessions"
            subtitle={
              policy.role_assignment_managed
                ? 'Role assignments follow organization SSO groups. Administrators can revoke existing sessions.'
                : 'Assign workspace roles with confirmation, or revoke sessions after an access change.'
            }
          >
            {users.isPending ? (
              <Loading />
            ) : users.error ? (
              <ErrorState error={users.error} />
            ) : !users.data?.items.length ? (
              <Empty title="No workspace users found" />
            ) : (
              <>
                <div className="access-user-list">
                  {users.data.items.map((account) => (
                    <div className="access-user" key={account.user_id}>
                      <div>
                        <strong>{account.display_name || account.email}</strong>
                        <p>{account.email}</p>
                      </div>
                      {canAssign ? (
                        <select
                          aria-label={`Role for ${account.email}`}
                          className="access-role-select"
                          value={
                            roleChange?.id === account.user_id ? roleChange.role : account.role
                          }
                          disabled={assign.isPending || revoke.isPending}
                          onChange={(event) => {
                            setConfirmation(null);
                            setRoleChange(
                              event.target.value === account.role
                                ? null
                                : {
                                    id: account.user_id,
                                    role: event.target.value as NonNullable<
                                      Schema<'UserPatch'>['role']
                                    >,
                                  },
                            );
                          }}
                        >
                          {policy.roles.map((role) => (
                            <option key={role.role} value={role.role}>
                              {role.label}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <span className="tag">{account.role}</span>
                      )}
                      {roleChange?.id === account.user_id ? (
                        <div
                          className="access-confirm"
                          role="group"
                          aria-label={`Confirm role change for ${account.email}`}
                        >
                          <span>Change to {roleChange.role}?</span>
                          <button
                            className="button small"
                            disabled={assign.isPending}
                            onClick={() => setRoleChange(null)}
                          >
                            Cancel
                          </button>
                          <button
                            className="button small primary"
                            disabled={assign.isPending}
                            onClick={() => assign.mutate(roleChange)}
                          >
                            {assign.isPending ? 'Updating…' : 'Confirm role change'}
                          </button>
                        </div>
                      ) : !canRevoke ? (
                        <span className="access-self-hint">Role management only</span>
                      ) : account.user_id === user.user_id ? (
                        <span className="access-self-hint">Current account · use Sign out</span>
                      ) : confirmation === account.user_id ? (
                        <div
                          className="access-confirm"
                          role="group"
                          aria-label={`Confirm session revocation for ${account.email}`}
                        >
                          <span>End all sessions?</span>
                          <button
                            className="button small"
                            disabled={revoke.isPending}
                            onClick={() => setConfirmation(null)}
                          >
                            Cancel
                          </button>
                          <button
                            className="button small danger"
                            disabled={revoke.isPending}
                            onClick={() => revoke.mutate(account.user_id)}
                          >
                            {revoke.isPending ? 'Revoking…' : 'Confirm revoke'}
                          </button>
                        </div>
                      ) : (
                        <button
                          className="button small"
                          disabled={assign.isPending || revoke.isPending}
                          onClick={() => {
                            setRoleChange(null);
                            setConfirmation(account.user_id);
                          }}
                        >
                          <LogOut size={13} />
                          Revoke sessions<span className="sr-only"> for {account.email}</span>
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <Pagination
                  total={users.data.total}
                  page={page}
                  onChange={(value) => {
                    setConfirmation(null);
                    setRoleChange(null);
                    set('page', String(value));
                  }}
                />
              </>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
