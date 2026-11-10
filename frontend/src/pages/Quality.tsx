import { useState } from 'react';
import { Select } from '../components/Select';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, FlaskConical, Pencil, Play, Plus, ShieldCheck } from 'lucide-react';
import { api, queryString } from '../api/client';
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
  plural,
  useFilters,
} from '../components/ui';
import './quality.css';

type Check = Schema<'QualityCheck'>;
type Input = Schema<'QualityCheckInput'>;
const kinds: { value: Input['kind']; label: string; hint: string }[] = [
  { value: 'null_rate', label: 'Null rate', hint: 'Measure missing values in one column.' },
  {
    value: 'duplicate_keys',
    label: 'Duplicate keys',
    hint: 'Find repeated keys within the sample, including null keys.',
  },
  {
    value: 'accepted_values',
    label: 'Accepted values',
    hint: 'Check values against an approved set. Null values fail.',
  },
  {
    value: 'schema_contract',
    label: 'Schema contract',
    hint: 'Compare catalog column names and types with your contract.',
  },
];
const outcome = (status: string) =>
  status === 'pass' ? 'success' : status === 'fail' ? 'failed' : 'warning';

export function Quality() {
  const { params, set, page } = useFilters();
  const tenant = params.get('tenant_id') || '';
  const selected = params.get('check_id') || '';
  const { isAdmin, canOperate, runtime, notify } = useApp();
  const [editor, setEditor] = useState<Check | 'new' | null>(null);
  const client = useQueryClient();
  const qs = queryString({ tenant_id: tenant, page });
  const checks = useQuery({
    queryKey: ['quality-checks', qs],
    queryFn: () => api<Schema<'QualityCheckPage'>>(`/quality/checks?${qs}`),
    placeholderData: keepPreviousData,
  });
  const history = useQuery({
    queryKey: ['quality-results', tenant, selected],
    queryFn: () =>
      api<Schema<'QualityResultPage'>>(
        `/quality/results?${queryString({ tenant_id: tenant, check_id: selected })}`,
      ),
    placeholderData: keepPreviousData,
  });
  const tenants = useQuery({
    queryKey: ['tenants-quality'],
    queryFn: () => api<Schema<'Page_Tenant_'>>('/tenants?page_size=200'),
  });
  const canWrite = isAdmin && runtime.live_actions_enabled;
  const canRun = canOperate && runtime.live_actions_enabled;
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['quality-checks'] });
    void client.invalidateQueries({ queryKey: ['quality-results'] });
  };
  const toggle = useMutation({
    mutationFn: (check: Check) =>
      api<Check>(`/quality/checks/${check.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ enabled: !check.enabled }),
      }),
    onSuccess: refresh,
    onError: (e) => notify(e.message),
  });
  const run = useMutation({
    mutationFn: (id: number) =>
      api<Schema<'QualityResult'>>(`/quality/checks/${id}/run`, { method: 'POST' }),
    onSuccess: (result) => {
      refresh();
      notify(
        `Check ${result.status === 'error' ? 'could not complete' : result.status === 'pass' ? 'passed' : 'found violations'}.`,
      );
    },
    onError: (e) => notify(e.message),
  });
  return (
    <>
      <PageHeader
        title="Data quality"
        description="Data quality checks on warehouse tables, evidenced by counts and rates."
        actions={
          canWrite && (
            <button className="button primary" onClick={() => setEditor('new')}>
              <Plus size={15} />
              New check
            </button>
          )
        }
      />
      <div className="notice info">
        <ShieldCheck size={18} />
        <div>
          <strong>
            {runtime.mode === 'demo'
              ? 'Simulated evidence, realistic checks'
              : 'Bounded reads, explicit contracts'}
          </strong>
          <p>
            {runtime.mode === 'demo'
              ? 'Demo results use synthetic rows and catalog snapshots. No warehouse is contacted.'
              : 'Sample checks return aggregate evidence only. A passing sample does not guarantee the entire table is correct. Live execution requires QUALITY_ENABLED.'}
          </p>
        </div>
      </div>
      {editor && (
        <CheckEditor
          initial={editor === 'new' ? undefined : editor}
          tenants={tenants.data?.items || []}
          defaultTenant={tenant}
          onClose={() => setEditor(null)}
          onSave={() => {
            setEditor(null);
            refresh();
          }}
        />
      )}
      <Panel
        title="Quality checks"
        subtitle="Scheduled checks use each tenant’s registered warehouse schema."
        className={checks.isPlaceholderData ? 'is-fetching' : ''}
      >
        <div className="filter-bar">
          <Select
            aria-label="Quality tenant"
            value={tenant}
            onChange={(e) => {
              set('tenant_id', e.target.value);
            }}
          >
            <option value="">All tenants</option>
            {tenants.data?.items.map((t) => (
              <option value={t.tenant_id} key={t.tenant_id}>
                {t.display_name}
              </option>
            ))}
          </Select>
          <span className="filter-count">
            {checks.data ? plural(checks.data.total, 'check') : '…'}
            {checks.data &&
              (() => {
                const failing = checks.data.items.filter(
                  (c) => c.latest_result && outcome(c.latest_result.status) === 'failed',
                ).length;
                return failing ? ` · ${plural(failing, 'failing check')}` : ' · none failing';
              })()}
          </span>
        </div>
        {checks.isPending ? (
          <Loading />
        ) : checks.error ? (
          <ErrorState error={checks.error} />
        ) : !checks.data.items.length ? (
          <Empty title="No quality checks configured">
            Create a bounded check for a registered tenant to start collecting evidence.
          </Empty>
        ) : (
          <>
            <div className="table-scroll">
              <table className="quality-table">
                <thead>
                  <tr>
                    <th>Check / tenant</th>
                    <th>Contract</th>
                    <th>Latest evidence</th>
                    <th>Schedule</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.data.items.map((check) => (
                    <tr
                      key={check.id}
                      className={selected === String(check.id) ? 'quality-selected' : ''}
                    >
                      <td>
                        <button
                          className="quality-title"
                          onClick={() => set('check_id', String(check.id))}
                        >
                          {check.name}
                        </button>
                        <TenantLink id={check.tenant_id} />
                      </td>
                      <td>
                        <strong>{kinds.find((k) => k.value === check.kind)?.label}</strong>
                        <code>{check.table_name}</code>
                        <small>
                          {check.kind === 'schema_contract'
                            ? 'Catalog inspection'
                            : `Up to ${check.sample_limit.toLocaleString()} rows`}
                        </small>
                      </td>
                      <td>
                        {check.latest_result ? (
                          <>
                            <StatusPill status={outcome(check.latest_result.status)} />
                            <small>
                              {check.latest_result.simulated ? 'Simulated · ' : ''}
                              {check.kind !== 'schema_contract' &&
                                `${check.latest_result.sampled_rows} sampled · `}
                              <Time value={check.latest_result.checked_at} relative />
                            </small>
                          </>
                        ) : (
                          <span className="muted">Awaiting evaluation</span>
                        )}
                      </td>
                      <td>
                        <StatusPill status={check.enabled ? 'enabled' : 'paused'} />
                        <small>Every {Math.round(check.interval_sec / 60)} min</small>
                      </td>
                      <td>
                        <div className="quality-actions">
                          <button
                            className="button small"
                            disabled={!canRun || !check.enabled || run.isPending}
                            onClick={() => run.mutate(check.id)}
                            aria-label={`Run ${check.name}`}
                          >
                            <Play size={13} />
                            Run
                          </button>
                          {canWrite && (
                            <>
                              <button
                                className="button small"
                                onClick={() => setEditor(check)}
                                aria-label={`Edit ${check.name}`}
                              >
                                <Pencil size={13} />
                              </button>
                              <button
                                className="button small"
                                disabled={toggle.isPending}
                                onClick={() => toggle.mutate(check)}
                              >
                                {check.enabled ? 'Disable' : 'Enable'}
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination
              total={checks.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
          </>
        )}
      </Panel>
      <Panel
        title={selected ? 'Check evidence' : 'Recent evidence'}
        subtitle="Only counts, rates, and schema differences are stored. Warehouse row values stay in the warehouse. Select an entry to filter to its check."
        className={history.isPlaceholderData ? 'is-fetching' : ''}
        action={
          selected && (
            <button className="button small" onClick={() => set('check_id', '')}>
              Show all checks
            </button>
          )
        }
      >
        {history.isPending ? (
          <Loading />
        ) : history.error ? (
          <ErrorState error={history.error} />
        ) : !history.data.items.length ? (
          <Empty title="No evidence yet">
            Run an enabled check or wait for its next scheduled evaluation.
          </Empty>
        ) : (
          <div className="quality-evidence">
            {history.data.items.map((result) => (
              <article
                key={result.id}
                className="row-clickable"
                onClick={() => set('check_id', String(result.check_id))}
              >
                <div className="quality-evidence-header">
                  <StatusPill status={outcome(result.status)} />
                  <TenantLink id={result.tenant_id} />
                  <span className="muted">Check #{result.check_id}</span>
                  <Time value={result.checked_at} />
                  {result.simulated && (
                    <span className="tag">
                      <FlaskConical size={12} />
                      SIMULATED
                    </span>
                  )}
                </div>
                <div className="quality-evidence-details">
                  {Object.entries(result.details).map(([key, value]) => (
                    <span key={key}>
                      <strong>{key.replaceAll('_', ' ')}</strong>
                      {Array.isArray(value)
                        ? value.join(', ') || 'None'
                        : typeof value === 'object'
                          ? JSON.stringify(value)
                          : String(value)}
                    </span>
                  ))}
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

function CheckEditor({
  initial,
  tenants,
  defaultTenant,
  onClose,
  onSave,
}: {
  initial?: Check;
  tenants: Schema<'Tenant'>[];
  defaultTenant: string;
  onClose: () => void;
  onSave: () => void;
}) {
  const { notify } = useApp();
  const [kind, setKind] = useState<Input['kind']>(initial?.kind || 'null_rate');
  const [tenant, setTenant] = useState(
    initial?.tenant_id || defaultTenant || tenants[0]?.tenant_id || '',
  );
  const [name, setName] = useState(initial?.name || '');
  const [table, setTable] = useState(initial?.table_name || 'orders');
  const [column, setColumn] = useState(String(initial?.params.column || 'amount'));
  const [columns, setColumns] = useState(
    Array.isArray(initial?.params.columns) ? initial.params.columns.join(', ') : 'id',
  );
  const [values, setValues] = useState(
    Array.isArray(initial?.params.values) ? initial.params.values.join('\n') : 'pending\ncomplete',
  );
  const [contract, setContract] = useState(
    initial?.kind === 'schema_contract'
      ? Object.entries(initial.params.columns as Record<string, string>)
          .map(([k, v]) => `${k}: ${v}`)
          .join('\n')
      : 'id: bigint\ncreated_at: timestamp\namount: numeric',
  );
  const [extra, setExtra] = useState(
    initial?.kind === 'schema_contract' ? Boolean(initial.params.allow_extra) : true,
  );
  const [rate, setRate] = useState(
    Number(
      initial?.params.max_null_rate ??
        initial?.params.max_duplicate_rate ??
        initial?.params.max_invalid_rate ??
        0,
    ) * 100,
  );
  const [sample, setSample] = useState(initial?.sample_limit || 1000);
  const [interval, setInterval] = useState((initial?.interval_sec || 900) / 60);
  const save = useMutation({
    mutationFn: (input: Input) =>
      api<Check>(initial ? `/quality/checks/${initial.id}` : '/quality/checks', {
        method: initial ? 'PUT' : 'POST',
        body: JSON.stringify(input),
      }),
    onSuccess: onSave,
    onError: (e) => notify(e.message),
  });
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const params: Input['params'] =
      kind === 'null_rate'
        ? { column, max_null_rate: rate / 100 }
        : kind === 'duplicate_keys'
          ? {
              columns: columns
                .split(',')
                .map((v) => v.trim())
                .filter(Boolean),
              max_duplicate_rate: rate / 100,
            }
          : kind === 'accepted_values'
            ? {
                column,
                values: values.split('\n').filter((v) => v !== ''),
                max_invalid_rate: rate / 100,
              }
            : {
                columns: Object.fromEntries(
                  contract
                    .split('\n')
                    .filter(Boolean)
                    .map((line) => {
                      const split = line.indexOf(':');
                      return split < 1
                        ? [line, '']
                        : [line.slice(0, split).trim(), line.slice(split + 1).trim()];
                    }),
                ),
                allow_extra: extra,
              };
    save.mutate({
      tenant_id: tenant,
      name,
      table_name: table,
      kind,
      params,
      sample_limit: sample,
      interval_sec: interval * 60,
      enabled: initial?.enabled ?? true,
    });
  };
  return (
    <Panel
      title={initial ? 'Edit quality check' : 'New quality check'}
      subtitle="Choose a built-in contract. Reads are restricted to this tenant’s registered schema."
      action={
        <button className="button small" onClick={onClose}>
          Cancel
        </button>
      }
    >
      <form className="quality-form" onSubmit={submit}>
        <label>
          Tenant
          <Select
            aria-label="Check tenant"
            required
            disabled={Boolean(initial)}
            value={tenant}
            onChange={(e) => setTenant(e.target.value)}
          >
            <option value="">Choose tenant</option>
            {tenants.map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.display_name}
              </option>
            ))}
          </Select>
        </label>
        <label>
          Check name
          <input required maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Table
          <input
            required
            value={table}
            onChange={(e) => setTable(e.target.value)}
            pattern="[A-Za-z_][A-Za-z0-9_]{0,62}"
          />
        </label>
        <label>
          Check type
          <Select value={kind} onChange={(e) => setKind(e.target.value as Input['kind'])}>
            {kinds.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </Select>
          <small>{kinds.find((k) => k.value === kind)?.hint}</small>
        </label>
        {(kind === 'null_rate' || kind === 'accepted_values') && (
          <label>
            Column
            <input required value={column} onChange={(e) => setColumn(e.target.value)} />
          </label>
        )}
        {kind === 'duplicate_keys' && (
          <label>
            Key columns
            <input required value={columns} onChange={(e) => setColumns(e.target.value)} />
            <small>Comma-separated names, at most eight.</small>
          </label>
        )}
        {kind === 'accepted_values' && (
          <label className="quality-wide">
            Accepted values
            <textarea
              required
              rows={4}
              value={values}
              onChange={(e) => setValues(e.target.value)}
            />
            <small>
              One value per line; compared using the warehouse value’s string representation.
            </small>
          </label>
        )}
        {kind === 'schema_contract' ? (
          <>
            <label className="quality-wide">
              Expected columns
              <textarea
                required
                rows={5}
                value={contract}
                onChange={(e) => setContract(e.target.value)}
              />
              <small>One column: information_schema type per line.</small>
            </label>
            <label className="quality-checkbox">
              <input type="checkbox" checked={extra} onChange={(e) => setExtra(e.target.checked)} />
              Allow extra columns
            </label>
          </>
        ) : (
          <>
            <label>
              Maximum violation rate (%)
              <input
                required
                type="number"
                min={0}
                max={100}
                step="any"
                value={rate}
                onChange={(e) => setRate(Number(e.target.value))}
              />
            </label>
            <label>
              Sample limit
              <input
                required
                type="number"
                min={1}
                max={10000}
                value={sample}
                onChange={(e) => setSample(Number(e.target.value))}
              />
            </label>
          </>
        )}
        <label>
          Evaluate every (minutes)
          <input
            required
            type="number"
            min={1}
            max={1440}
            value={interval}
            onChange={(e) => setInterval(Number(e.target.value))}
          />
        </label>
        <div className="quality-wide quality-form-footer">
          <span className="muted">
            {initial
              ? 'Previous evidence remains in history. The updated contract awaits a new evaluation.'
              : 'Only aggregate evidence is saved.'}
          </span>
          <button className="button primary" disabled={save.isPending || !tenant}>
            <CheckCircle2 size={15} />
            {save.isPending ? 'Saving…' : 'Save check'}
          </button>
        </div>
      </form>
    </Panel>
  );
}
