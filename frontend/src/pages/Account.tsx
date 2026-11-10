import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useApp } from '../AppContext';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { PageHeader, Panel } from '../components/ui';
import { Select } from '../components/Select';

export function Account() {
  const { user, runtime, notify, textSize, setTextSize, isAdmin, access } = useApp();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const change = useMutation({
    mutationFn: () =>
      api<Schema<'Message'>>('/auth/password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      }),
    onSuccess: (r) => {
      setCurrent('');
      setNext('');
      notify(r.message);
    },
    onError: (e) => notify(e.message),
  });
  return (
    <>
      <PageHeader
        title="Account settings"
        description="Manage your sign-in, appearance, and workspace identity."
      />
      <Panel title="Your account">
        <div className="governance-link">
          <div>
            <strong>{user.display_name}</strong>
            <p>
              {user.email} · {user.role}
            </p>
          </div>
        </div>
      </Panel>
      <Panel title="Display" subtitle="Text size for this console, saved on this device.">
        <form className="settings-form" onSubmit={(event) => event.preventDefault()}>
          <label>
            Text size
            <Select
              aria-label="Text size"
              value={textSize}
              onChange={(event) => setTextSize(event.target.value)}
            >
              <option value="standard">Standard</option>
              <option value="large">Large</option>
            </Select>
          </label>
        </form>
      </Panel>
      {isAdmin && (
        <Panel
          title="Admin privileges"
          subtitle="Review and manage the controls available to your administrator account."
        >
          <div className="governance-link">
            <div>
              <strong>
                {access?.permissions.filter(
                  (permission) => permission.minimum_role === 'admin' && permission.enabled,
                ).length ?? 0}{' '}
                admin controls available
              </strong>
              <p>
                Create users, assign roles, grant user permissions, revoke sessions, configure
                workspace operations, and review audit history.
              </p>
            </div>
            <Link className="button small" to="/admin?section=users">
              Manage users
            </Link>
            <Link className="button small" to="/admin?section=roles">
              Manage roles
            </Link>
            <Link className="button small" to="/access">
              Privilege access
            </Link>
          </div>
        </Panel>
      )}
      <Panel
        title="Password"
        subtitle={
          runtime.auth_provider === 'oidc'
            ? 'Your organization manages your password.'
            : 'Choose a password of at least 12 characters. Other sessions will be signed out.'
        }
      >
        {runtime.auth_provider === 'oidc' ? (
          <div className="governance-link">
            Use your organization’s identity provider to change your password.
          </div>
        ) : (
          <form
            className="settings-form"
            onSubmit={(event) => {
              event.preventDefault();
              change.mutate();
            }}
          >
            <label>
              Current password
              <input
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(event) => setCurrent(event.target.value)}
                required
              />
            </label>
            <label>
              New password
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
                value={next}
                onChange={(event) => setNext(event.target.value)}
                required
              />
            </label>
            <button className="button primary" disabled={change.isPending}>
              Update password
            </button>
          </form>
        )}
      </Panel>
    </>
  );
}
