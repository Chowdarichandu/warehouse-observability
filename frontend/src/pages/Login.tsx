import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Database, GitBranch, Layers3, ShieldCheck, Workflow } from 'lucide-react';
import { api, setCsrf } from '../api/client';
import type { Schema } from '../api/client';
import { APP_NAME } from '../config';

export function Login({ config }: { config: Schema<'RuntimeConfig'> }) {
  const [email, setEmail] = useState('admin@demo.local');
  const [password, setPassword] = useState('');
  const client = useQueryClient();
  const [forgotOpen, setForgotOpen] = useState(false);
  const forgot = useMutation({
    mutationFn: () =>
      api<Schema<'ForgotPasswordResult'>>('/auth/forgot-password', {
        method: 'POST',
        body: JSON.stringify({ email }),
      }),
  });
  const login = useMutation({
    mutationFn: () =>
      api<Schema<'User'>>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      }),
    onSuccess: (user) => {
      setCsrf(user.csrf_token || '');
      client.setQueryData(['me'], user);
    },
  });
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <span className="brand-icon">
            <Workflow size={23} />
          </span>
          <span>{APP_NAME}</span>
        </div>
        <div className="login-copy">
          <span className="eyebrow">WAREHOUSE OBSERVABILITY</span>
          <h1>
            Pipeline
            <br />
            operations.
          </h1>
          <p>
            Run health, data freshness, and alert history,
            <br />
            in one place for the data team.
          </p>
          <div className="pipeline-art">
            <div>
              <Database />
              <span>Sources</span>
            </div>
            <i />
            <div>
              <GitBranch />
              <span>Airbyte</span>
            </div>
            <i />
            <div>
              <Layers3 />
              <span>Warehouse</span>
            </div>
          </div>
          <div className="login-health">
            <span className="pulse-dot" /> MySQL and MongoDB ingestion monitoring.
          </div>
        </div>
        <div className="login-footer">
          MySQL & MongoDB <span>→</span> Airbyte <span>→</span> Airflow <span>→</span> Warehouse
        </div>
      </div>
      <main className="login-form-wrap">
        <form
          className="login-form"
          onSubmit={(event) => {
            event.preventDefault();
            login.mutate();
          }}
        >
          <div className="demo-label">
            <span /> {config.environment.toUpperCase()}
          </div>
          <h2>Welcome back</h2>
          <p>Sign in to your pipeline workspace.</p>
          {config.auth_provider === 'oidc' ? (
            <a className="button primary login-submit" href="/api/auth/oidc/start">
              Continue with organization SSO <ArrowRight size={16} />
            </a>
          ) : (
            <>
              <label>
                Email address
                <input
                  autoComplete="username"
                  type="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              </label>
              <label>
                Password
                <input
                  autoComplete="current-password"
                  type="password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  required
                />
              </label>
              {login.error && (
                <p role="alert" className="danger-text">
                  {login.error.message}
                </p>
              )}
              <button
                className="button primary login-submit"
                type="submit"
                disabled={login.isPending}
              >
                {login.isPending ? 'Signing in…' : 'Sign in to workspace'}
                <ArrowRight size={16} />
              </button>
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setForgotOpen(!forgotOpen);
                  forgot.reset();
                }}
              >
                Forgot your password?
              </button>
              {forgotOpen && (
                <div className="forgot-box">
                  <p>
                    Enter your account email above and we’ll reset it. In this demo workspace a
                    temporary password is shown here directly; in a live workspace an administrator
                    resets it from Administration → Users & roles.
                  </p>
                  <button
                    type="button"
                    className="button small"
                    disabled={forgot.isPending || !email}
                    onClick={() => forgot.mutate()}
                  >
                    {forgot.isPending ? 'Resetting…' : 'Reset my password'}
                  </button>
                  {forgot.error && (
                    <p role="alert" className="danger-text">
                      {forgot.error.message}
                    </p>
                  )}
                  {forgot.data && (
                    <div className="forgot-result">
                      <p>{forgot.data.message}</p>
                      {forgot.data.temporary_password && (
                        <p className="temp-password mono">{forgot.data.temporary_password}</p>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
          {config.mode === 'demo' && (
            <>
              <div className="demo-credentials">
                <ShieldCheck size={18} />
                <div>
                  <strong>Explore the demo</strong>
                  <p>
                    Use admin@demo.local, operator@demo.local, or viewer@demo.local. Default
                    password: <code>demo</code>.
                  </p>
                </div>
              </div>
              <p className="login-note">
                Demo data is fictional. All actions are simulated locally.
              </p>
            </>
          )}
          {config.mode === 'live' && (
            <p className="login-note">
              Access is managed by your organization. Contact the data platform team for access.
            </p>
          )}
        </form>
      </main>
    </div>
  );
}
