import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CheckCheck, ChevronDown, UserRound, X } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { Select } from '../components/Select';
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
  formatDateTime,
  formatDuration,
  plural,
  useFilters,
} from '../components/ui';

const CAUSE_CATEGORIES = [
  'Source system',
  'Sync / CDC',
  'Schema change',
  'Data volume',
  'Platform / infrastructure',
  'Configuration',
  'Other',
];

function ruleLabel(rule?: string | null) {
  return rule ? rule.replaceAll('_', ' ') : '';
}

function timeOpen(incident: Schema<'Incident'>) {
  const end = incident.resolved_at ? new Date(incident.resolved_at) : new Date();
  const seconds = Math.max(0, (end.getTime() - new Date(incident.opened_at).getTime()) / 1000);
  return formatDuration(seconds);
}

function alertTitle(alert: Schema<'Alert'>) {
  const suffix = alert.tenant_id ? ` · ${alert.tenant_id}` : '';
  return suffix && alert.title.endsWith(suffix)
    ? alert.title.slice(0, -suffix.length)
    : alert.title;
}

type TimelineEvent = {
  at: string;
  label: string;
  detail?: string;
  body?: string;
};

function timeline(detail: Schema<'IncidentDetail'>): TimelineEvent[] {
  const events: TimelineEvent[] = [
    {
      at: detail.opened_at,
      label: 'Incident opened',
      detail: detail.cause_rule ? `Cause: ${ruleLabel(detail.cause_rule)}` : undefined,
    },
  ];
  if (detail.acknowledged_at)
    events.push({
      at: detail.acknowledged_at,
      label: 'Acknowledged',
      detail: detail.acknowledged_by ? `by ${detail.acknowledged_by}` : undefined,
    });
  for (const note of detail.notes)
    events.push({ at: note.created_at, label: `Note by ${note.author}`, body: note.body });
  if (detail.resolved_at)
    events.push({
      at: detail.resolved_at,
      label: 'Resolved',
      detail: [
        detail.resolved_by ? `by ${detail.resolved_by}` : '',
        detail.root_cause_category ? `Root cause: ${detail.root_cause_category}` : '',
      ]
        .filter(Boolean)
        .join(' · '),
    });
  return events.sort((a, b) => a.at.localeCompare(b.at));
}

function IncidentDetailPanel({ id }: { id: string }) {
  const { canOperate, notify } = useApp();
  const client = useQueryClient();
  const [resolving, setResolving] = useState(false);
  const [category, setCategory] = useState('');
  const [assignee, setAssignee] = useState<string | null>(null);
  const [noteBody, setNoteBody] = useState('');
  const detail = useQuery({
    queryKey: ['incident', id],
    queryFn: () => api<Schema<'IncidentDetail'>>(`/incidents/${id}`),
  });
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['incidents'] });
    void client.invalidateQueries({ queryKey: ['incident', id] });
    void client.invalidateQueries({ queryKey: ['alerts'] });
  };
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) =>
      api<Schema<'Message'>>(`/incidents/${id}/${path}`, {
        method: 'POST',
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      }),
    onSuccess: (result) => {
      notify(result.message);
      setResolving(false);
      refresh();
    },
    onError: (error) => notify(error.message),
  });
  const noteMutation = useMutation({
    mutationFn: (body: string) =>
      api<Schema<'IncidentNote'>>(`/incidents/${id}/notes`, {
        method: 'POST',
        body: JSON.stringify({ body }),
      }),
    onSuccess: () => {
      setNoteBody('');
      refresh();
    },
    onError: (error) => notify(error.message),
  });
  if (detail.isPending) return <Loading />;
  if (detail.error) return <ErrorState error={detail.error} />;
  const incident = detail.data;
  const assigneeValue = assignee ?? incident.assignee ?? '';
  return (
    <Panel
      title={incident.title}
      action={
        <>
          <StatusPill status={incident.severity} />
          <StatusPill status={incident.state === 'open' ? 'firing' : incident.state} />
        </>
      }
    >
      <p className="muted">
        {incident.tenant_id ? (
          <>
            <TenantLink id={incident.tenant_id} /> ·{' '}
          </>
        ) : null}
        {incident.source_type ? `${incident.source_type === 'mongo' ? 'MongoDB' : 'MySQL'} · ` : ''}
        Opened <Time value={incident.opened_at} relative /> · {timeOpen(incident)} open
        {incident.assignee ? ` · Assigned to ${incident.assignee}` : ''}
      </p>
      {canOperate && incident.state !== 'resolved' && (
        <div className="filter-bar">
          {incident.state === 'open' && (
            <button
              className="button small"
              disabled={action.isPending}
              onClick={() => action.mutate({ path: 'ack' })}
            >
              <CheckCheck size={14} /> Acknowledge
            </button>
          )}
          {!resolving ? (
            <button
              className="button small"
              disabled={action.isPending}
              onClick={() => setResolving(true)}
            >
              <Check size={14} /> Resolve
            </button>
          ) : (
            <>
              <Select
                aria-label="Root cause category (optional)"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
              >
                <option value="">Root cause: not recorded</option>
                {CAUSE_CATEGORIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </Select>
              <button
                className="button small primary"
                disabled={action.isPending}
                onClick={() =>
                  action.mutate({
                    path: 'resolve',
                    body: { root_cause_category: category || null },
                  })
                }
              >
                {action.isPending ? 'Resolving…' : 'Confirm resolve'}
              </button>
              <button
                className="button small"
                disabled={action.isPending}
                onClick={() => setResolving(false)}
              >
                <X size={14} /> Cancel
              </button>
            </>
          )}
          <span className="assign-control">
            <UserRound size={14} />
            <input
              aria-label="Assignee"
              placeholder="Assign to (name or email)"
              value={assigneeValue}
              onChange={(event) => setAssignee(event.target.value)}
            />
            <button
              className="button small"
              disabled={action.isPending || assigneeValue === (incident.assignee ?? '')}
              onClick={() => action.mutate({ path: 'assign', body: { assignee: assigneeValue } })}
            >
              Save
            </button>
          </span>
        </div>
      )}
      <div className="incident-columns">
        <div>
          <h3 className="section-label">Timeline</h3>
          <ul className="investigation-timeline">
            {timeline(incident).map((event, index) => (
              <li key={index}>
                <span className="event-marker" />
                <span className="muted">{formatDateTime(event.at)}</span>
                <div>
                  <strong>{event.label}</strong>
                  {event.detail && <p className="muted">{event.detail}</p>}
                  {event.body && <p>{event.body}</p>}
                </div>
              </li>
            ))}
          </ul>
          {canOperate && (
            <div className="note-form">
              <textarea
                aria-label="Add a note"
                placeholder="Add a note for the team…"
                rows={2}
                value={noteBody}
                onChange={(event) => setNoteBody(event.target.value)}
              />
              <button
                className="button small"
                disabled={!noteBody.trim() || noteMutation.isPending}
                onClick={() => noteMutation.mutate(noteBody.trim())}
              >
                {noteMutation.isPending ? 'Adding…' : 'Add note'}
              </button>
            </div>
          )}
        </div>
        <div>
          <h3 className="section-label">Alerts in this incident ({incident.alerts.length})</h3>
          {incident.alerts.length === 0 ? (
            <p className="muted">No alerts are attached to this incident.</p>
          ) : (
            <ul className="incident-alerts">
              {incident.alerts.map((alert) => (
                <li key={alert.id}>
                  <StatusPill status={alert.state} />
                  <div>
                    <strong>{alertTitle(alert)}</strong>
                    <p className="muted">
                      {ruleLabel(alert.rule_id)} · first fired{' '}
                      <Time value={alert.first_fired_at} relative />
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {incident.tenant_id && (
            <p>
              <Link to={`/alerts?tenant=${incident.tenant_id}`}>View this tenant's alerts</Link>
            </p>
          )}
        </div>
      </div>
    </Panel>
  );
}

export function Incidents() {
  const { params, set, page } = useFilters();
  const state = params.get('state') || '';
  const tenant = params.get('tenant') || '';
  const selected = params.get('incident') || '';
  const query = useQuery({
    queryKey: ['incidents', state, tenant, page],
    queryFn: () =>
      api<Schema<'Page_Incident_'>>(`/incidents?state=${state}&tenant=${tenant}&page=${page}`),
  });
  const tenants = useQuery({
    queryKey: ['tenants', 'incident-filter'],
    queryFn: () => api<Schema<'Page_Tenant_'>>('/tenants?page=1&page_size=100'),
  });
  return (
    <>
      <PageHeader
        title="Incidents"
        description="Related alerts grouped into one incident per tenant and source, with one notification thread."
      />
      <Panel className={query.isPlaceholderData ? 'is-fetching' : ''}>
        <div className="filter-bar">
          <Select
            aria-label="Filter by tenant"
            value={tenant}
            onChange={(event) => set('tenant', event.target.value)}
          >
            <option value="">All tenants</option>
            {(tenants.data?.items ?? []).map((item) => (
              <option key={item.tenant_id} value={item.tenant_id}>
                {item.display_name}
              </option>
            ))}
          </Select>
          {tenant && (
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
          )}
        </div>
        <div className="tabs">
          {[
            ['', 'All incidents'],
            ['open', 'Open'],
            ['acknowledged', 'Acknowledged'],
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
        ) : !query.data?.items.length ? (
          <Empty title="No incidents in this view" />
        ) : (
          <>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Severity</th>
                    <th>Incident</th>
                    <th>Tenant</th>
                    <th>Opened</th>
                    <th>Time open</th>
                    <th>State</th>
                    <th>Assignee</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((incident) => (
                    <tr
                      key={incident.id}
                      className={selected === incident.id ? 'selected-row' : ''}
                    >
                      <td>
                        <StatusPill status={incident.severity} />
                      </td>
                      <td>
                        <button
                          className="group-button"
                          onClick={() =>
                            set('incident', selected === incident.id ? '' : incident.id)
                          }
                        >
                          <span className="incident-title">{incident.title}</span>
                          <span>
                            {incident.cause_rule
                              ? `Cause: ${ruleLabel(incident.cause_rule)}`
                              : 'Grouped alerts'}
                            {incident.source_type
                              ? ` · ${incident.source_type === 'mongo' ? 'MongoDB' : 'MySQL'}`
                              : ''}
                          </span>
                        </button>
                      </td>
                      <td>
                        {incident.tenant_id ? (
                          <TenantLink id={incident.tenant_id} />
                        ) : (
                          <span className="muted">Platform</span>
                        )}
                      </td>
                      <td>
                        <Time value={incident.opened_at} />
                        <small className="block muted">
                          <Time value={incident.opened_at} relative />
                        </small>
                      </td>
                      <td>{timeOpen(incident)}</td>
                      <td>
                        <StatusPill
                          status={incident.state === 'open' ? 'firing' : incident.state}
                        />
                      </td>
                      <td>{incident.assignee || <span className="muted">Unassigned</span>}</td>
                      <td>
                        <ChevronDown
                          size={15}
                          className={
                            selected === incident.id ? 'incident-chevron open' : 'incident-chevron'
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              page={page}
              size={query.data.page_size}
              total={query.data.total}
              onChange={(next) => set('page', String(next))}
            />
            <p className="muted">
              {plural(query.data.total, 'incident')} · grouped by tenant and source
            </p>
          </>
        )}
      </Panel>
      {selected && <IncidentDetailPanel id={selected} />}
    </>
  );
}
