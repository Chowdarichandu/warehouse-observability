import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { Download, ExternalLink, FileText, LockKeyhole, RefreshCw, Search } from 'lucide-react';
import { api, queryString, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { Chart } from '../components/Chart';
import { RunsTable } from '../components/RunsTable';
import { EventTimeline, RunComparison, SavedRunViews } from '../components/Investigation';
import { StatusPill } from '../components/StatusPill';
import {
  Back,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Pagination,
  Panel,
  Source,
  TenantLink,
  Time,
  formatDuration,
  useFilters,
} from '../components/ui';

export function Runs() {
  const { params, set, rangeQuery, page } = useFilters();
  const filters = ['tenant', 'status', 'source', 'load', 'stage', 'error_class', 'q', 'sort'];
  const qs = `${rangeQuery}&${queryString(Object.fromEntries(filters.map((k) => [k, params.get(k) || ''])))}&page=${page}`;
  const query = useQuery({
    queryKey: ['runs', qs],
    queryFn: () => api<Schema<'Page_Run_'>>(`/runs?${qs}`),
  });
  const options = [
    {
      key: 'status',
      label: 'All statuses',
      values: ['success', 'failed', 'running', 'queued', 'cancelled', 'skipped'],
    },
    { key: 'source', label: 'All sources', values: ['mysql', 'mongo'] },
    { key: 'load', label: 'All load types', values: ['initial', 'cdc'] },
    { key: 'stage', label: 'All stages', values: ['airflow', 'airbyte', 'warehouse'] },
  ];
  return (
    <>
      <PageHeader
        title="Pipeline runs"
        description="Trace every run from orchestration to the warehouse."
        actions={
          <a className="button" href={`/api/runs?${qs}&format=csv`}>
            <Download size={14} />
            Export CSV
          </a>
        }
      />
      <SavedRunViews />
      <Panel>
        <div className="filter-bar wrapping">
          <label className="search-field">
            <Search size={15} />
            <input
              aria-label="Search runs"
              placeholder="Search runs, errors, or logs…"
              value={params.get('q') || ''}
              onChange={(e) => set('q', e.target.value)}
            />
          </label>
          {options.map((option) => (
            <select
              key={option.key}
              aria-label={option.label}
              value={params.get(option.key) || ''}
              onChange={(e) => set(option.key, e.target.value)}
            >
              <option value="">{option.label}</option>
              {option.values.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          ))}
          <input
            className="compact-input"
            aria-label="Tenant slug filter"
            placeholder="Tenant slug"
            value={params.get('tenant') || ''}
            onChange={(e) => set('tenant', e.target.value)}
          />
          <input
            className="compact-input"
            aria-label="Error class filter"
            placeholder="Error class"
            value={params.get('error_class') || ''}
            onChange={(e) => set('error_class', e.target.value)}
          />
          {filters.some((key) => params.has(key)) && (
            <Link className="text-link" to={`/runs?${rangeQuery}`}>
              Clear filters
            </Link>
          )}
        </div>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : (
          <>
            <RunsTable
              runs={query.data.items}
              onSort={(field) =>
                set('sort', params.get('sort') === `-${field}` ? field : `-${field}`)
              }
            />
            <Pagination
              total={query.data.total}
              page={page}
              onChange={(p) => set('page', String(p))}
            />
          </>
        )}
      </Panel>
    </>
  );
}

export function RunDetail() {
  const { key = '' } = useParams();
  const { params: detailParams } = useFilters();
  const focusLog = detailParams.get('focus') === 'log';
  const { canMutatePipelines: canOperate, notify, runtime } = useApp();
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: ['run', key],
    queryFn: () => api<Schema<'RunDetail'>>(runPath(key)),
  });
  const log = useQuery({
    queryKey: ['log', key],
    queryFn: () => api<Schema<'Log'>>(`${runPath(key)}/log`),
  });
  useEffect(() => {
    if (focusLog && !log.isPending && !query.isPending)
      document.getElementById('run-log')?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      });
  }, [key, focusLog, log.isPending, query.isPending]);
  const retry = useMutation({
    mutationFn: () => api<Schema<'RetryResult'>>(`${runPath(key)}/retry`, { method: 'POST' }),
    onSuccess: (result) => {
      notify(result.message);
      void client.invalidateQueries();
      navigate(runPath(result.run_key));
    },
    onError: (error) => notify(error.message),
  });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const { run, error, streams, previous_runs, usual_duration_s } = query.data;
  return (
    <>
      <Back to={`/runs?tenant=${run.tenant_id}`}>Pipeline runs</Back>
      <PageHeader
        eyebrow="RUN INVESTIGATION"
        title={`${run.source_type === 'mysql' ? 'MySQL' : 'MongoDB'} ${run.load_type.toUpperCase()} sync`}
        description={`${run.tenant_id} · ${run.triggered_by === 'retry' ? 'Retry attempt' : 'Scheduled pipeline run'}`}
        actions={
          <>
            <StatusPill status={run.status} />
            <button
              className="button primary"
              disabled={
                !canOperate || !['failed', 'cancelled'].includes(run.status) || retry.isPending
              }
              onClick={() => retry.mutate()}
              title={
                !canOperate
                  ? 'Operator access and enabled actions required'
                  : runtime.mode === 'demo'
                    ? 'Simulated in demo mode'
                    : 'Retry this run upstream'
              }
            >
              <RefreshCw size={14} />
              {retry.isPending ? 'Starting retry…' : 'Retry run'}
            </button>
          </>
        }
      />
      {run.triggered_by === 'retry' && (
        <div className="notice info">
          <RefreshCw size={19} />
          <div>
            <strong>
              {runtime.mode === 'demo' ? 'Simulated retry' : 'Retry attempt'} ·{' '}
              {run.status === 'running' ? 'In progress' : run.status}
            </strong>
            <p>
              {runtime.mode === 'demo'
                ? 'This new attempt completes after about 30 seconds. Acme’s missing binlog still requires a resync, even when a task retry completes.'
                : 'This retry was accepted upstream. Status will update when the collector observes the next attempt.'}
            </p>
          </div>
        </div>
      )}
      <div className="detail-kpis">
        <div>
          <span>Tenant</span>
          <TenantLink id={run.tenant_id} />
        </div>
        <div>
          <span>Duration</span>
          <strong>
            {formatDuration(run.duration_s)}
            <small> usual {formatDuration(usual_duration_s)}</small>
          </strong>
        </div>
        <div>
          <span>Queue delay</span>
          <strong>{formatDuration(run.queue_delay_s)}</strong>
        </div>
        <div>
          <span>Rows synced</span>
          <strong>
            <NumberValue value={run.rows_synced} />
          </strong>
        </div>
        <div>
          <span>Attempts</span>
          <strong>
            {run.airbyte_attempts || 1}
            <small> Airbyte</small>
          </strong>
        </div>
      </div>
      {error && (
        <div className="error-diagnosis">
          <div className="diagnosis-heading">
            <span className="status-dot red" />
            <strong className="mono">{error.error_class}</strong>
            <StatusPill status={error.severity === 'critical' ? 'critical' : 'failed'} />
            <span className="tag">
              {error.stage} · {error.failure_origin}
            </span>
          </div>
          <p>{error.error_message}</p>
          <div className="fix-hint">
            <span>RECOMMENDED ACTION</span>
            <strong>{error.hint}</strong>
          </div>
        </div>
      )}
      <div className="two-column">
        <Panel title="Airflow orchestration" action={<span className="tag">TASK INSTANCE</span>}>
          <dl className="metadata-list">
            <dt>DAG</dt>
            <dd className="mono">{run.dag_id || 'Not triggered by Airflow'}</dd>
            <dt>Task</dt>
            <dd className="mono">{run.task_id || '—'}</dd>
            <dt>DAG run</dt>
            <dd className="mono break-all">{run.dag_run_id || '—'}</dd>
            <dt>Map index / try</dt>
            <dd>
              {run.map_index} / {run.try_number}
            </dd>
            <dt>Queued</dt>
            <dd>
              <Time value={run.queued_at} />
            </dd>
            <dt>Started</dt>
            <dd>
              <Time value={run.started_at} />
            </dd>
            <dt>Ended</dt>
            <dd>
              <Time value={run.ended_at} />
            </dd>
          </dl>
        </Panel>
        <Panel title="Airbyte replication" action={<Source source={run.source_type} />}>
          <dl className="metadata-list">
            <dt>Job ID</dt>
            <dd className="mono">{run.airbyte_job_id || '—'}</dd>
            <dt>Connection</dt>
            <dd className="mono break-all">{run.airbyte_connection_id || '—'}</dd>
            <dt>Attempts</dt>
            <dd>{run.airbyte_attempts || 1}</dd>
            <dt>Failure origin</dt>
            <dd>{error?.failure_origin || 'None'}</dd>
            <dt>Failure type</dt>
            <dd>{error?.error_class || 'None'}</dd>
            <dt>Data transferred</dt>
            <dd>
              <NumberValue value={(run.bytes_synced || 0) / 1024 / 1024} suffix=" MB" />
            </dd>
            <dt>Run key</dt>
            <dd className="mono break-all">{run.run_key}</dd>
          </dl>
        </Panel>
      </div>
      <div id="run-log">
        <Panel
          title="Run log"
          subtitle="Redacted at collection and again before display."
          action={
            <span className="redacted-label">
              <LockKeyhole size={12} />
              SECRETS REDACTED
            </span>
          }
        >
          {log.isPending ? (
            <Loading />
          ) : log.error ? (
            <ErrorState error={log.error} />
          ) : (
            <LogViewer content={log.data.content} />
          )}
        </Panel>
      </div>
      {!!streams.length && (
        <Panel title="Per-stream record counts" subtitle="Counts reported by the sync job">
          <Chart
            label="Records synced by stream"
            option={{
              grid: { left: 110, right: 40, top: 10, bottom: 30 },
              xAxis: { type: 'value', splitLine: { lineStyle: { color: '#81909f22' } } },
              yAxis: {
                type: 'category',
                data: streams.map((s) => s.stream_name),
                axisLabel: { color: '#81909f' },
              },
              series: [
                {
                  type: 'bar',
                  barMaxWidth: 14,
                  itemStyle: { color: '#4e9c86', borderRadius: [0, 3, 3, 0] },
                  data: streams.map((s) => s.records),
                },
              ],
            }}
          />
        </Panel>
      )}
      <RunComparison current={query.data} previous={previous_runs} />
      <EventTimeline runKey={run.run_key} tenant={run.tenant_id} rangeQuery={runRange(run)} />
      <Panel
        title="Previous runs"
        subtitle="The previous 10 runs of this tenant, source, and load type"
      >
        <RunsTable runs={previous_runs} />
      </Panel>
    </>
  );
}

function runRange(run: Schema<'Run'>) {
  const start = new Date(run.queued_at || run.started_at || run.collected_at).getTime() - 3600000;
  const end = Math.min(
    new Date(run.ended_at || run.collected_at).getTime() + 3600000,
    start + 90 * 86400000,
  );
  return `from=${encodeURIComponent(new Date(start).toISOString())}&to=${encodeURIComponent(new Date(end).toISOString())}`;
}

function LogViewer({ content }: { content: string }) {
  const { params, set } = useFilters();
  const [wrap, setWrap] = useState(true);
  const [matchIndex, setMatchIndex] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const onlyMatches = params.get('logfilter') === 'matches';
  const term = params.get('logq') || '';
  const lines = content.split('\n');
  const matches = lines.flatMap((line, index) =>
    term && line.toLowerCase().includes(term.toLowerCase()) ? [index] : [],
  );
  const matchingLines = new Set(matches);
  function nextMatch(direction: number) {
    if (!matches.length) return;
    const next = (matchIndex + direction + matches.length) % matches.length;
    setMatchIndex(next);
    logRef.current
      ?.querySelector(`[data-line="${matches[next]}"]`)
      ?.scrollIntoView({ block: 'nearest', behavior: 'auto' });
  }
  function download() {
    const url = URL.createObjectURL(new Blob([content], { type: 'text/plain' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'redacted-run.log';
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <>
      <div className="log-toolbar">
        <span>
          <FileText size={14} />
          {lines.length} lines
        </span>
        <label className="search-field">
          <Search size={14} />
          <input
            aria-label="Search within log"
            placeholder="Find in log…"
            value={term}
            onChange={(e) => {
              set('logq', e.target.value);
              setMatchIndex(0);
            }}
          />
        </label>
        <button
          className="button small"
          disabled={!matches.length}
          aria-label="Previous log match"
          onClick={() => nextMatch(-1)}
        >
          Previous
        </button>
        <button
          className="button small"
          disabled={!matches.length}
          aria-label="Next log match"
          onClick={() => nextMatch(1)}
        >
          Next
        </button>
        <label className="inline-flex">
          <input
            type="checkbox"
            checked={onlyMatches}
            onChange={(e) => set('logfilter', e.target.checked ? 'matches' : '')}
          />
          Matching lines only
        </label>
        <button className="text-button" onClick={() => setWrap(!wrap)}>
          {wrap ? 'Disable wrap' : 'Wrap lines'}
        </button>
        <button className="button small" onClick={download}>
          <Download size={13} />
          Download log
        </button>
      </div>
      <div
        ref={logRef}
        className={`log-viewer ${wrap ? 'wrap-lines' : ''}`}
        role="region"
        aria-label="Redacted run log"
      >
        <ol>
          {lines.map(
            (line, index) =>
              (!onlyMatches || !term || matchingLines.has(index)) && (
                <li
                  key={index}
                  data-line={index}
                  className={`${/error/i.test(line) ? 'error-line' : ''} ${term && line.toLowerCase().includes(term.toLowerCase()) ? 'log-match' : ''}`}
                >
                  <span>{index + 1}</span>
                  <code>{line || ' '}</code>
                </li>
              ),
          )}
        </ol>
      </div>
      {term && (
        <div className="panel-footer">
          {matches.length
            ? `${Math.min(matchIndex + 1, matches.length)} of ${matches.length} matching lines`
            : 'No matching lines'}{' '}
          <ExternalLink size={12} />
        </div>
      )}
    </>
  );
}
