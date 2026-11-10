import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useApp } from '../AppContext';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { PageHeader, Panel } from '../components/ui';

export function Account() {
  const { user, runtime, notify } = useApp();
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
        description="Manage your sign-in and review your workspace identity."
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
            onSubmit={(e) => {
              e.preventDefault();
              change.mutate();
            }}
          >
            <label>
              Current password
              <input
                type="password"
                autoComplete="current-password"
                value={current}
                onChange={(e) => setCurrent(e.target.value)}
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
                onChange={(e) => setNext(e.target.value)}
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
