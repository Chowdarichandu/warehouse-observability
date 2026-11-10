import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Select } from '../components/Select';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bell, Check, CheckCheck, ChevronDown, Mail, Send, Settings2 } from 'lucide-react';
import { api } from '../api/client';
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
  TenantLink,
  Time,
  displayTenantName,
  useFilters,
} from '../components/ui';

function alertTitle(alert: Schema<'Alert'>) {
  const suffix = alert.tenant_id ? ` · ${alert.tenant_id}` : '';
  return suffix && alert.title.endsWith(suffix)
    ? alert.title.slice(0, -suffix.length)
    : alert.title;
}

export function Alerts() {
  const { params, set, page } = useFilters();
  const state = params.get('state') || '';
  const tenant = params.get('tenant') || '';
  const [expanded, setExpanded] = useState<number | null>(null);
  const { canOperate, isAdmin, notify } = useApp();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['alerts', state, tenant, page],
    queryFn: () =>
      api<Schema<'Page_Alert_'>>(`/alerts?state=${state}&tenant=${tenant}&page=${page}`),
  });
  const rules = useQuery({
    queryKey: ['rules'],
    queryFn: () => api<Schema<'Page_Rule_'>>('/alert-rules'),
    enabled: isAdmin,
  });
  const channels = useQuery({
    queryKey: ['channels'],
    queryFn: () => api<Schema<'Page_Channel_'>>('/channels'),
    enabled: isAdmin,
  });
  const action = useMutation({
    mutationFn: ({ id, type }: { id: number; type: string }) =>
      api<Schema<'Message'>>(`/alerts/${id}/${type}`, { method: 'POST' }),
    onSuccess: (r) => {
      notify(r.message);
      void client.invalidateQueries();
    },
    onError: (e) => notify(e.message),
  });
  const test = useMutation({
    mutationFn: (id: string) => api<Schema<'Message'>>(`/channels/${id}/test`, { method: 'POST' }),
    onSuccess: (r) => notify(r.message),
    onError: (e) => notify(e.message),
  });
  return (
    <>
      <PageHeader
        title="Alerts"
        description="Alerts from your pipelines. Acknowledge, investigate, and track recovery."
        actions={
          <span className="tag">
            <Bell size={13} />
            EVALUATED EVERY MINUTE
          </span>
        }
      />
      <Panel className={query.isPlaceholderData ? 'is-fetching' : ''}>
        {tenant && (
          <div className="filter-bar">
            <span className="tag">
              Tenant: {displayTenantName(tenant)}
              <button
                className="tag-clear"
                aria-label="Clear tenant filter"
                onClick={() => set('tenant', '')}
              >
                ×
              </button>
            </span>
          </div>
        )}
        <div className="tabs">
          {[
            ['', 'All alerts'],
            ['firing', 'Firing'],
            ['acked', 'Acknowledged'],
            ['resolved', 'Resolved'],
          ].map(([value, label]) => (
            <button
              className={state === value ? 'active' : ''}
              key={value}
              onClick={() => set('state', value)}
            >
              {label}
              {value === state && query.data && !query.isPlaceholderData && (
                <span>{query.data.total}</span>
              )}
            </button>
          ))}
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : query.data.items.length ? (
          <>
            <div className="alerts-list">
              {query.data.items.map((alert) => (
                <div className={`alert-card severity-${alert.severity}`} key={alert.id}>
                  <div className="alert-card-icon">
                    <Bell size={19} />
                  </div>
                  <div className="alert-card-body">
                    <div className="inline-flex">
                      <StatusPill status={alert.severity} />
                      <StatusPill status={alert.state} />
                      <span className="muted mono">#{alert.id}</span>
                    </div>
                    <button
                      className="alert-title-button"
                      aria-expanded={expanded === alert.id}
                      onClick={() => setExpanded(expanded === alert.id ? null : alert.id)}
                    >
                      <h3>{alertTitle(alert)}</h3>
                      <ChevronDown
                        size={15}
                        className={expanded === alert.id ? 'chevron-open' : ''}
                      />
                    </button>
                    <p>
                      {String(
                        alert.details?.reason ||
                          alert.details?.hint ||
                          alert.rule_id.replaceAll('_', ' '),
                      )}
                    </p>
                    {expanded === alert.id && (
                      <div className="alert-details">
                        <dl>
                          <div>
                            <dt>Rule</dt>
                            <dd>{alert.rule_id.replaceAll('_', ' ')}</dd>
                          </div>
                          {Object.entries(alert.details || {})
                            .filter(([key]) => !['reason', 'hint', 'tenant_id'].includes(key))
                            .map(([key, value]) => (
                              <div key={key}>
                                <dt>{key.replaceAll('_', ' ')}</dt>
                                <dd>{String(value)}</dd>
                              </div>
                            ))}
                        </dl>
                        {alert.tenant_id && (
                          <Link className="text-link" to={`/runs?tenant=${alert.tenant_id}`}>
                            View this tenant's runs
                          </Link>
                        )}
                      </div>
                    )}
                    <div className="alert-meta">
                      {alert.tenant_id && <TenantLink id={alert.tenant_id} />}
                      <span>
                        First fired <Time value={alert.first_fired_at} relative />
                      </span>
                      {alert.acked_at && (
                        <span>
                          Acknowledged <Time value={alert.acked_at} relative />
                        </span>
                      )}
                      {alert.resolved_at && (
                        <span>
                          Resolved <Time value={alert.resolved_at} relative />
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="alert-actions">
                    {alert.state === 'firing' && (
                      <button
                        className="button small"
                        disabled={!canOperate || action.isPending}
                        onClick={() => action.mutate({ id: alert.id, type: 'ack' })}
                      >
                        <Check size={13} />
                        Acknowledge
                      </button>
                    )}
                    {alert.state !== 'resolved' && (
                      <button
                        className="button small"
                        disabled={!canOperate || action.isPending}
                        onClick={() => action.mutate({ id: alert.id, type: 'resolve' })}
                      >
                        <CheckCheck size={13} />
                        Resolve
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
            <Pagination
              total={query.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
          </>
        ) : (
          <Empty title="No alerts in this state">
            Resolved alerts remain available in the history tab.
          </Empty>
        )}
      </Panel>
      {isAdmin && (
        <>
          <Panel
            title="Notification channels"
            subtitle="Test deliveries are recorded locally in demo mode. No external messages are sent."
          >
            {channels.isPending ? (
              <Loading />
            ) : channels.error ? (
              <ErrorState error={channels.error} />
            ) : (
              <div className="channels-grid">
                {channels.data?.items.map((channel) => (
                  <div className="channel-card" key={channel.channel_id}>
                    <span className="channel-icon">
                      {channel.kind === 'email' ? <Mail size={21} /> : <Send size={21} />}
                    </span>
                    <div>
                      <strong>{channel.channel_id}</strong>
                      <small>
                        {channel.kind} · {channel.enabled ? 'Enabled' : 'Disabled'}
                      </small>
                    </div>
                    <button
                      className="button small"
                      disabled={test.isPending || !channel.enabled}
                      onClick={() => test.mutate(channel.channel_id)}
                    >
                      <Send size={12} />
                      Send test
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel
            title="Alert rules"
            subtitle="Built-in rule types. Only parameters and delivery settings can be edited."
            action={<Settings2 size={17} />}
          >
            {rules.isPending ? (
              <Loading />
            ) : rules.error ? (
              <ErrorState error={rules.error} />
            ) : (
              rules.data?.items.map((rule) => (
                <RuleEditor key={rule.rule_id} rule={rule} channels={channels.data?.items || []} />
              ))
            )}
          </Panel>
        </>
      )}
    </>
  );
}

function RuleEditor({ rule, channels }: { rule: Schema<'Rule'>; channels: Schema<'Channel'>[] }) {
  const [open, setOpen] = useState(false);
  const { notify } = useApp();
  const client = useQueryClient();
  const update = useMutation({
    mutationFn: (data: Schema<'RulePatch'>) =>
      api<Schema<'Rule'>>(`/alert-rules/${rule.rule_id}`, {
        method: 'PUT',
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      notify('Alert rule updated.');
      void client.invalidateQueries({ queryKey: ['rules'] });
      setOpen(false);
    },
    onError: (e) => notify(e.message),
  });
  return (
    <div className="rule-item">
      <button className="rule-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={`toggle-dot ${rule.enabled ? 'enabled' : ''}`} />
        <span>
          <strong>{rule.name}</strong>
          <small>{rule.rule_id}</small>
        </span>
        <StatusPill status={rule.severity} />
        <ChevronDown size={15} />
      </button>
      {open && (
        <form
          className="rule-form"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            update.mutate({
              severity: String(data.get('severity')) as Schema<'RulePatch'>['severity'],
              params: Object.fromEntries(
                Object.keys(rule.params || {}).map((key) => [key, Number(data.get(key))]),
              ),
              enabled: data.get('enabled') === 'on',
              repeat_min: Number(data.get('repeat_min')),
              channels: data.getAll('channels').map(String),
            });
          }}
        >
          <label>
            Severity
            <Select name="severity" defaultValue={rule.severity}>
              {['critical', 'high', 'medium', 'low'].map((s) => (
                <option key={s} value={s}>
                  {s[0].toUpperCase() + s.slice(1)}
                </option>
              ))}
            </Select>
          </label>
          {Object.entries(rule.params || {}).map(([key, value]) => (
            <label key={key}>
              {{
                pct: 'Threshold (%)',
                drop_pct: 'Drop (%)',
                n: 'Consecutive failures',
                multiplier: 'Duration multiplier (×)',
                consecutive_failures: 'Consecutive failures',
                minutes: 'Window (minutes)',
                count: 'Count',
              }[key] ?? key.replaceAll('_', ' ').replace(/^\w/, (c) => c.toUpperCase())}
              <input name={key} type="number" min="1" max="10080" defaultValue={value} required />
            </label>
          ))}
          <label>
            Repeat after (minutes)
            <input
              name="repeat_min"
              type="number"
              min="1"
              defaultValue={rule.repeat_min}
              required
            />
          </label>
          <label className="checkbox-label">
            <input type="checkbox" name="enabled" defaultChecked={rule.enabled} />
            Rule enabled
          </label>
          <div className="channel-checks">
            {channels.map((channel) => (
              <label className="checkbox-label" key={channel.channel_id}>
                <input
                  type="checkbox"
                  name="channels"
                  value={channel.channel_id}
                  defaultChecked={rule.channels.includes(channel.channel_id)}
                />
                {channel.channel_id}
              </label>
            ))}
          </div>
          <button className="button primary" disabled={update.isPending}>
            Save rule
          </button>
        </form>
      )}
    </div>
  );
}
