import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Circle,
  Clock3,
  Database,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  Pause,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { api, runPath } from '../../api/client';
import type { Schema } from '../../api/client';
import { useApp } from '../../AppContext';
import { ErrorState, Loading, Time } from '../ui';
import { StatusPill } from '../StatusPill';

type Dag = Schema<'OnboardDag'>;
type ProgressData = Schema<'OnboardProgress'>;
const STATE_LABELS: Record<string, string> = {
  pending: 'Not started',
  queued: 'Queued',
  running: 'Running',
  success: 'Complete',
  failed: 'Failed',
  blocked: 'Blocked',
  skipped: 'Not selected',
  uncertain: 'Needs review',
  awaiting_initial: 'Awaiting initial load',
};
function duration(
  start: string | null | undefined,
  end: string | null | undefined,
  now: number,
): string {
  if (!start) return '—';
  const seconds = Math.max(
    0,
    Math.floor(((end ? new Date(end).getTime() : now) - new Date(start).getTime()) / 1000),
  );
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
function StateIcon({ status }: { status: string }) {
  if (status === 'success') return <CheckCircle2 size={19} />;
  if (status === 'failed' || status === 'uncertain') return <TriangleAlert size={19} />;
  if (status === 'running') return <LoaderCircle size={19} className="journey-spin" />;
  if (status === 'blocked') return <LockKeyhole size={18} />;
  if (status === 'awaiting_initial' || status === 'skipped') return <Pause size={18} />;
  if (status === 'queued') return <Clock3 size={18} />;
  return <Circle size={18} />;
}
function DagCard({ dag, now }: { dag: Dag; now: number }) {
  return (
    <article
      className={`journey-dag state-${dag.status}`}
      aria-label={`${dag.label}: ${STATE_LABELS[dag.status] || dag.status}`}
    >
      <div className="journey-dag-top">
        <span className="journey-node-icon">
          <StateIcon status={dag.status} />
        </span>
        <span className="journey-stage-kind">
          {dag.phase === 'provision'
            ? '01 · Provision'
            : dag.phase === 'initial'
              ? '02 · Initial load'
              : dag.phase === 'cdc'
                ? '03 · Continuous sync'
                : 'Coordinator'}
        </span>
        <span className="journey-state-label">{STATE_LABELS[dag.status] || dag.status}</span>
      </div>
      <h3>{dag.label}</h3>
      <code className="journey-dag-id">{dag.dag_id}</code>
      {dag.blocked_reason && <p className="journey-dag-reason">{dag.blocked_reason}</p>}
      {dag.last_error && (
        <p className="journey-dag-error">
          <TriangleAlert size={14} />
          {dag.last_error}
        </p>
      )}
      <div className="journey-dag-meta">
        <span>
          <Clock3 size={12} />
          {duration(dag.started_at, dag.ended_at, now)}
        </span>
        <span>Attempt {dag.attempt}</span>
      </div>
      {dag.tasks.length > 0 && (
        <details className="journey-task-list">
          <summary>
            {dag.tasks.length} tasks <span>Inspect execution</span>
          </summary>
          <ol>
            {dag.tasks.map((task) => (
              <li key={task.task_id}>
                <StateIcon status={task.status} />
                <div>
                  <strong>{task.label}</strong>
                  <small>{task.last_error || STATE_LABELS[task.status] || task.status}</small>
                </div>
                <span>{duration(task.started_at, task.ended_at, now)}</span>
              </li>
            ))}
          </ol>
        </details>
      )}
      {dag.run_key ? (
        <Link className="journey-dag-link" to={runPath(dag.run_key)}>
          Inspect child run <ArrowRight size={13} />
        </Link>
      ) : dag.dag_run_id ? (
        <details className="journey-run-reference">
          <summary>Execution reference</summary>
          <code>{dag.dag_run_id}</code>
        </details>
      ) : null}
    </article>
  );
}
export function OnboardingProgress({ tenant }: { tenant: string }) {
  const { can, notify } = useApp();
  const client = useQueryClient();
  const progress = useQuery({
    queryKey: ['onboarding', tenant],
    queryFn: () => api<ProgressData>(`/onboarding/${encodeURIComponent(tenant)}`),
    refetchInterval: (query) => (query.state.data?.workflow_status === 'running' ? 2000 : 30000),
    retry: false,
  });
  const [now, setNow] = useState(Date.now());
  const data = progress.data;
  const active = data?.workflow_status === 'running';
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  const resume = useMutation({
    mutationFn: () =>
      api<ProgressData>(`/onboarding/${encodeURIComponent(tenant)}/resume`, {
        method: 'POST',
        body: JSON.stringify({ start_initial: true }),
      }),
    onSuccess: (result) => {
      client.setQueryData(['onboarding', tenant], result);
      void client.invalidateQueries({ queryKey: ['tenants'] });
      notify('Workflow resumed from its saved progress.');
    },
    onError: (e) => notify(e.message),
  });
  if (progress.isPending) return <Loading />;
  if (progress.error)
    return (
      <>
        <Link className="journey-back-link" to="/tenants">
          <ArrowLeft size={15} />
          Tenants
        </Link>
        <ErrorState error={progress.error} />
      </>
    );
  if (!data) return null;
  if (!data.dags.length)
    return (
      <div className="tenant-journey">
        <div className="journey-access">
          <GitBranch size={28} />
          <h1>No activation workflow recorded</h1>
          <p>
            This tenant has no seven-DAG activation record. You can inspect its existing pipeline
            activity in the tenant workspace.
          </p>
          <Link className="button" to={`/tenants/${encodeURIComponent(tenant)}`}>
            Open tenant <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    );
  const complete = data.workflow_status === 'success';
  const failed = data.workflow_status === 'failed' || data.workflow_status === 'uncertain';
  const awaiting = data.workflow_status === 'awaiting_initial';
  const done = data.dags.filter((dag) => dag.status === 'success').length;
  const skipped = data.dags.filter((dag) => dag.status === 'skipped').length;
  const coordinator = data.dags.find((dag) => dag.node_id === 'coordinator');
  const title = complete
    ? 'Your tenant is ready'
    : awaiting
      ? 'Provisioned. Initial load is waiting.'
      : failed
        ? 'This workflow needs attention'
        : 'Bringing your tenant online';
  const end = active ? undefined : data.updated_at;
  return (
    <div className="tenant-journey journey-progress-page">
      {!can('onboarding.start') && (
        <div className="journey-reader-note">
          <ShieldCheck size={16} />
          <p>
            You have read-only access to this workflow. An authorized operator can start or resume
            execution.
          </p>
        </div>
      )}
      <div className="journey-page-top">
        <Link className="journey-back-link" to="/tenants">
          <ArrowLeft size={15} />
          All tenants
        </Link>
        <span className="journey-top-context">ONBOARDING / {tenant}</span>
      </div>
      <header className="journey-progress-heading">
        <div>
          <span className="journey-eyebrow">TENANT ACTIVATION</span>
          <h1>{title}</h1>
          <p>
            {data.display_name} <span>·</span>{' '}
            {data.simulated ? 'Local demonstration' : 'Persisted workflow execution'}
          </p>
        </div>
        <Link className="button" to={`/tenants/${encodeURIComponent(tenant)}`}>
          Open tenant <ArrowRight size={14} />
        </Link>
      </header>
      <section
        className={`journey-execution-summary ${failed ? 'needs-attention' : ''}`}
        aria-label="Workflow execution summary"
      >
        <div className="journey-execution-status">
          <span className={`journey-execution-symbol ${complete ? 'is-complete' : ''}`}>
            {complete ? (
              <Check size={23} />
            ) : failed ? (
              <TriangleAlert size={23} />
            ) : awaiting ? (
              <Pause size={23} />
            ) : (
              <GitBranch size={23} />
            )}
          </span>
          <div>
            <strong>
              {complete
                ? 'All selected pipelines verified'
                : awaiting
                  ? 'Waiting for an operator'
                  : failed
                    ? 'Progress saved. Investigate before continuing.'
                    : 'One coordinator. Two independent source branches.'}
            </strong>
            <p>
              {done} of {data.dags.length} DAGs complete{skipped ? ` · ${skipped} skipped` : ''}
            </p>
          </div>
        </div>
        <div className="journey-execution-metrics">
          <div>
            <span>Elapsed</span>
            <strong>{duration(data.created_at, end, now)}</strong>
          </div>
          <div>
            <span>Started</span>
            <strong>
              <Time value={data.created_at} />
            </strong>
          </div>
          <div>
            <span>Workflow</span>
            <code title={data.workflow_id || undefined}>
              {data.workflow_id?.slice(0, 8) || '—'}
            </code>
          </div>
        </div>
        <div
          className="journey-completion-track"
          role="progressbar"
          aria-label="Onboarding DAG completion"
          aria-valuenow={done + skipped}
          aria-valuemin={0}
          aria-valuemax={data.dags.length}
        >
          <i
            style={{
              width: `${data.dags.length ? ((done + skipped) / data.dags.length) * 100 : 0}%`,
            }}
          />
        </div>
      </section>
      {(failed || awaiting) && (
        <section className={`journey-recovery ${failed ? 'is-failed' : ''}`} role="status">
          <div>
            {failed ? <TriangleAlert size={20} /> : <Pause size={20} />}
            <div>
              <h2>
                {awaiting
                  ? 'Start the initial loads when you are ready'
                  : data.workflow_status === 'uncertain'
                    ? 'Confirm the upstream outcome'
                    : 'Resume after the failure is resolved'}
              </h2>
              <p>
                {data.resume_reason ||
                  (awaiting
                    ? 'CDC remains blocked until initial loads complete successfully.'
                    : 'Completed stages are retained. The affected stage will be retried.')}
              </p>
            </div>
          </div>
          {data.can_resume && (
            <button
              className="button primary"
              disabled={!can('onboarding.start') || resume.isPending}
              onClick={() => resume.mutate()}
            >
              <RefreshCw size={14} />
              {resume.isPending
                ? 'Resuming…'
                : awaiting
                  ? 'Start initial loads'
                  : 'Resume workflow'}
            </button>
          )}
        </section>
      )}
      {coordinator && (
        <div className="journey-coordinator">
          <div className="journey-coordinator-label">
            <GitBranch size={15} />
            <span>WORKFLOW ORCHESTRATION</span>
            <span className="journey-orchestration-line" />
          </div>
          <DagCard dag={coordinator} now={now} />
        </div>
      )}
      <div className="journey-branches">
        {(['mysql', 'mongo'] as const).map((source) => {
          const dags = data.dags.filter((dag) => dag.source_type === source);
          const disabled = dags.length > 0 && dags.every((dag) => dag.status === 'skipped');
          return (
            <section
              className={`journey-branch ${disabled ? 'branch-skipped' : ''}`}
              key={source}
              aria-label={`${source === 'mysql' ? 'MySQL' : 'MongoDB'} pipeline branch`}
            >
              <header>
                <span className={`journey-source-icon ${source}`}>
                  <Database size={19} />
                </span>
                <div>
                  <h2>{source === 'mysql' ? 'MySQL' : 'MongoDB'}</h2>
                  <p>
                    {disabled
                      ? 'Source not selected'
                      : source === 'mysql'
                        ? 'Provision → snapshot → binlog CDC'
                        : 'Provision → snapshot → change streams'}
                  </p>
                </div>
                {disabled && <StatusPill status="skipped" />}
              </header>
              <div className="journey-branch-stages">
                {dags.map((dag) => (
                  <DagCard key={dag.node_id} dag={dag} now={now} />
                ))}
              </div>
            </section>
          );
        })}
      </div>
      <section className="journey-history">
        <div className="journey-section-heading">
          <div>
            <span className="journey-eyebrow">AUDITABLE PROGRESS</span>
            <h2>Execution timeline</h2>
          </div>
          <span>{data.events.length} recorded events</span>
        </div>
        {data.events.length ? (
          <ol>
            {data.events
              .slice()
              .reverse()
              .map((event) => (
                <li key={event.id}>
                  <span className={`journey-history-dot state-${event.status}`} />
                  <div>
                    <strong>{event.step}</strong>
                    <p>{event.message}</p>
                  </div>
                  <StatusPill status={event.status === 'ok' ? 'success' : event.status} />
                  <Time value={event.at} />
                </li>
              ))}
          </ol>
        ) : (
          <p className="journey-empty-copy">
            The coordinator has not recorded an execution event yet.
          </p>
        )}
      </section>
      {complete && (
        <div className="journey-finish">
          <CheckCircle2 size={22} />
          <div>
            <strong>{data.display_name} is ready for operations.</strong>
            <span>
              Keep following freshness, quality and pipeline health from the tenant workspace.
            </span>
          </div>
          <Link className="button primary" to={`/tenants/${encodeURIComponent(tenant)}`}>
            Open tenant <ArrowRight size={14} />
          </Link>
          <Link className="button" to="/">
            Back to overview
          </Link>
        </div>
      )}
    </div>
  );
}
