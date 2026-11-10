import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Circle,
  Database,
  KeyRound,
  LoaderCircle,
  Rocket,
  ShieldCheck,
  Workflow,
} from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { StatusPill } from '../components/StatusPill';
import { ONBOARDING_FINAL_STEP, dagsFor } from '../onboardingPlan';

const DAG_IDS: Record<string, string> = {
  onboarding: 'tenant_onboarding',
  'mysql-provisioning': 'mysql_provisioning',
  'mongo-provisioning': 'mongodb_provisioning',
  'mysql-initial': 'mysql_initial_load',
  'mongo-initial': 'mongodb_initial_load',
  'mysql-cdc': 'mysql_cdc',
  'mongo-cdc': 'mongodb_cdc',
};
import { ErrorState, Loading, PageHeader, Panel, useFilters } from '../components/ui';

const INITIAL: Schema<'OnboardInput'> = {
  tenant_id: 'zenith_pay',
  display_name: 'Zenith Pay',
  has_mysql: true,
  has_mongo: true,
  mysql_host: 'mysql.zenith.internal',
  mysql_port: 3306,
  mysql_database: 'payments',
  mysql_user: 'replication_reader',
  mysql_secret_ref: 'demo://zenith/mysql',
  mongo_database: 'payments',
  mongo_secret_ref: 'demo://zenith/mongo',
  warehouse_schema: 'zenith_pay',
  freshness_sla_min: 120,
  owner_email: 'data@zenith.example',
  run_initial: true,
};
export function Onboarding() {
  const { params, set } = useFilters();
  const { canMutatePipelines: canOperate, notify, runtime } = useApp();
  const step = Math.max(1, Math.min(4, Number(params.get('step') || 1)));
  const tenant = params.get('tenant') || '';
  const [draft, setDraft] = useState<Schema<'OnboardInput'>>(() => {
    try {
      return (
        JSON.parse(sessionStorage.getItem(`obs-onboard-draft-${runtime.mode}`) || 'null') ||
        (runtime.mode === 'demo'
          ? INITIAL
          : {
              ...INITIAL,
              tenant_id: '',
              display_name: '',
              mysql_host: '',
              mysql_database: '',
              mysql_secret_ref: 'aws://observability/',
              mongo_secret_ref: 'aws://observability/',
              warehouse_schema: '',
              owner_email: '',
            })
      );
    } catch {
      return INITIAL;
    }
  });
  function update<K extends keyof Schema<'OnboardInput'>>(
    key: K,
    value: Schema<'OnboardInput'>[K],
  ) {
    const next = { ...draft, [key]: value };
    setDraft(next);
    sessionStorage.setItem(`obs-onboard-draft-${runtime.mode}`, JSON.stringify(next));
  }
  const preflight = useMutation({
    mutationFn: () =>
      api<Schema<'Preflight'>>('/onboarding/preflight', {
        method: 'POST',
        body: JSON.stringify(draft),
      }),
    onError: (e) => notify(e.message),
  });
  const start = useMutation({
    mutationFn: () =>
      api<Schema<'OnboardProgress'>>('/onboarding', {
        method: 'POST',
        body: JSON.stringify(draft),
      }),
    onSuccess: (r) => {
      set('tenant', r.tenant_id);
      sessionStorage.removeItem(`obs-onboard-draft-${runtime.mode}`);
    },
    onError: (e) => notify(e.message),
  });
  const progress = useQuery({
    queryKey: ['onboarding', tenant],
    queryFn: () => api<Schema<'OnboardProgress'>>(`/onboarding/${tenant}`),
    enabled: !!tenant,
    refetchInterval: 2000,
  });
  const fields = (names: { key: keyof Schema<'OnboardInput'>; label: string; type?: string }[]) =>
    names.map(({ key, label, type }) => (
      <label key={key}>
        {label}
        <input
          type={type || 'text'}
          value={String(draft[key] ?? '')}
          onChange={(e) => update(key, type === 'number' ? Number(e.target.value) : e.target.value)}
          required={key !== 'warehouse_schema'}
        />
      </label>
    ));
  if (!canOperate)
    return (
      <>
        <PageHeader title="Onboard tenant" description="Register and connect a new client." />
        <div className="notice info">
          <ShieldCheck size={20} />
          <p>Onboarding requires the Operator or Admin role.</p>
        </div>
      </>
    );
  if (tenant)
    return (
      <>
        <PageHeader
          title={
            progress.data?.status === 'active'
              ? 'Your tenant is ready'
              : 'Bringing your tenant online'
          }
          description={`${tenant} · ${runtime.mode === 'demo' ? 'Simulated onboarding' : 'Airflow onboarding'}, streamed live.`}
        />
        {progress.isPending ? (
          <Loading />
        ) : progress.error ? (
          <ErrorState error={progress.error} />
        ) : (
          <Panel>
            <div className="onboard-progress">
              <div
                className={`progress-orb ${progress.data.status === 'active' ? 'complete' : ''}`}
              >
                {progress.data.status === 'active' ? (
                  <CheckCircle2 size={34} />
                ) : (
                  <LoaderCircle size={34} className="spin" />
                )}
              </div>
              <h2>
                {progress.data.status === 'active'
                  ? 'Connected. Synced. Observable.'
                  : 'Setting up your pipelines…'}
              </h2>
              <p>
                Seven DAGs run in sequence — onboarding, provisioning, initial load and CDC for each
                source. Steps take about 90 seconds in total.
              </p>
              <div className="journey">
                {dagsFor(draft).map((dag, dagIndex, all) => {
                  const states = dag.steps.map((name) => {
                    const event = progress.data.events
                      .slice()
                      .reverse()
                      .find((e) => e.step === name);
                    return { name, event };
                  });
                  const doneCount = states.filter((s) => s.event?.status === 'ok').length;
                  const failed = states.some((s) => s.event?.status === 'failed');
                  const dagState = failed
                    ? 'failed'
                    : doneCount === states.length
                      ? 'done'
                      : states.some((s) => s.event)
                        ? 'active'
                        : 'pending';
                  const stateLabel =
                    dagState === 'done'
                      ? 'Passed'
                      : dagState === 'active'
                        ? 'Running'
                        : dagState === 'failed'
                          ? 'Failed'
                          : 'Queued';
                  const kind = dag.id.includes('provisioning')
                    ? 'PROVISION'
                    : dag.id.includes('initial')
                      ? 'INITIAL LOAD'
                      : dag.id.includes('cdc')
                        ? 'CONTINUOUS SYNC'
                        : 'COORDINATE';
                  const dagId = DAG_IDS[dag.id] || dag.id;
                  return (
                    <div key={dag.id} className={`journey-node ${dagState}`}>
                      <div className="journey-rail">
                        <span className="journey-icon">
                          {dagState === 'done' ? (
                            <CheckCircle2 size={19} />
                          ) : dagState === 'active' ? (
                            <LoaderCircle size={19} className="spin" />
                          ) : dag.source ? (
                            <Database size={17} />
                          ) : (
                            <Workflow size={17} />
                          )}
                        </span>
                        {dagIndex < all.length - 1 && <span className="journey-line" />}
                      </div>
                      <div className="journey-body">
                        <div className="journey-top">
                          <span className="journey-kind">{kind}</span>
                          <span className={`journey-state ${dagState}`}>{stateLabel}</span>
                        </div>
                        <h3>
                          {dagIndex + 1}. {dag.name}
                        </h3>
                        <code className="journey-dag-id">{dagId}</code>
                        {dagState === 'pending' && dagIndex > 0 && (
                          <p className="journey-note">
                            Waiting for {all[dagIndex - 1].name} to pass.
                          </p>
                        )}
                        <details className="journey-steps" open={dagState === 'active'}>
                          <summary>
                            {doneCount}/{states.length} steps
                          </summary>
                          <div className="onboard-steps">
                            {states.map(({ name, event }) => (
                              <div key={name} className={event?.status === 'ok' ? 'done' : ''}>
                                {event?.status === 'ok' ? (
                                  <CheckCircle2 size={17} />
                                ) : event?.status === 'started' ? (
                                  <LoaderCircle size={17} className="spin" />
                                ) : (
                                  <Circle size={17} />
                                )}
                                <span>{name}</span>
                                {event && (
                                  <StatusPill
                                    status={
                                      event.status === 'ok'
                                        ? 'success'
                                        : event.status === 'started'
                                          ? 'running'
                                          : 'failed'
                                    }
                                  />
                                )}
                              </div>
                            ))}
                          </div>
                        </details>
                      </div>
                    </div>
                  );
                })}
                {(() => {
                  const event = progress.data.events
                    .slice()
                    .reverse()
                    .find((e) => e.step === ONBOARDING_FINAL_STEP);
                  const state = event?.status === 'ok' ? 'done' : event ? 'active' : 'pending';
                  return (
                    <div className={`journey-node ${state}`}>
                      <div className="journey-rail">
                        <span className="journey-icon">
                          {state === 'done' ? (
                            <CheckCircle2 size={19} />
                          ) : state === 'active' ? (
                            <LoaderCircle size={19} className="spin" />
                          ) : (
                            <Rocket size={17} />
                          )}
                        </span>
                      </div>
                      <div className="journey-body">
                        <div className="journey-top">
                          <span className="journey-kind">ACTIVATE</span>
                          <span className={`journey-state ${state}`}>
                            {state === 'done' ? 'Live' : state === 'active' ? 'Running' : 'Queued'}
                          </span>
                        </div>
                        <h3>{ONBOARDING_FINAL_STEP}</h3>
                        <p className="journey-note">
                          The tenant goes live — pipelines, freshness and alerts switch on.
                        </p>
                      </div>
                    </div>
                  );
                })()}
              </div>
              {progress.data.status === 'active' && (
                <div className="inline-flex centered">
                  <Link className="button primary" to={`/tenants/${tenant}`}>
                    Open tenant <ArrowRight size={14} />
                  </Link>
                  <Link className="button" to="/">
                    Back to overview
                  </Link>
                </div>
              )}
            </div>
          </Panel>
        )}
      </>
    );
  return (
    <>
      <PageHeader
        title="Onboard a tenant"
        description="From a new client to healthy pipelines, in one guided flow."
        actions={
          <span className="tag">
            <ShieldCheck size={13} />
            SIMULATED DEMO
          </span>
        }
      />
      <div className="wizard-layout">
        <div className="wizard-sidebar">
          {['Tenant details', 'Data sources', 'Pre-flight checks', 'Review & start'].map(
            (label, i) => (
              <div className={step === i + 1 ? 'active' : step > i + 1 ? 'done' : ''} key={label}>
                <span>{step > i + 1 ? <Check size={14} /> : `0${i + 1}`}</span>
                <div>
                  <strong>{label}</strong>
                  <small>
                    {
                      [
                        'Name, owner and service level',
                        'Connections and secret references',
                        'Check CDC readiness',
                        'Bring your tenant online',
                      ][i]
                    }
                  </small>
                </div>
              </div>
            ),
          )}
          <div className="wizard-note">
            <KeyRound size={23} />
            <strong>Secrets stay in your vault.</strong>
            <p>Use secret manager references. Never enter database passwords here.</p>
          </div>
        </div>
        <Panel>
          <form
            className="wizard-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (step < 4) {
                set('step', String(step + 1));
                if (step === 2) preflight.mutate();
              } else start.mutate();
            }}
          >
            <div className="wizard-heading">
              <span className="eyebrow">STEP 0{step} OF 04</span>
              <h2>
                {
                  [
                    'Tell us about your tenant',
                    'Connect the data sources',
                    'Check your pipeline readiness',
                    'Ready when you are',
                  ][step - 1]
                }
              </h2>
              <p>
                {
                  [
                    'A unique identity and an owner for this workspace.',
                    'We use references to resolve credentials outside the console.',
                    'Demo checks simulate connectivity, replication settings, and permissions.',
                    'Review the configuration before starting the onboarding workflow.',
                  ][step - 1]
                }
              </p>
            </div>
            {step === 1 && (
              <div className="form-grid">
                {fields([
                  { key: 'display_name', label: 'Display name' },
                  { key: 'tenant_id', label: 'Tenant slug' },
                  { key: 'owner_email', label: 'Owner email', type: 'email' },
                  { key: 'warehouse_schema', label: 'Warehouse schema' },
                  { key: 'freshness_sla_min', label: 'Freshness SLA (minutes)', type: 'number' },
                ])}
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={draft.run_initial}
                    onChange={(e) => update('run_initial', e.target.checked)}
                  />
                  Run initial loads now
                </label>
              </div>
            )}
            {step === 2 && (
              <>
                <div className="source-form">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={draft.has_mysql}
                      onChange={(e) => update('has_mysql', e.target.checked)}
                    />
                    <strong>MySQL</strong>
                  </label>
                  {draft.has_mysql && (
                    <div className="form-grid">
                      {fields([
                        { key: 'mysql_host', label: 'Host' },
                        { key: 'mysql_port', label: 'Port', type: 'number' },
                        { key: 'mysql_database', label: 'Database' },
                        { key: 'mysql_user', label: 'Replication user' },
                        {
                          key: 'mysql_secret_ref',
                          label: 'Secret reference (aws:// in live mode)',
                        },
                      ])}
                    </div>
                  )}
                </div>
                <div className="source-form">
                  <label className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={draft.has_mongo}
                      onChange={(e) => update('has_mongo', e.target.checked)}
                    />
                    <strong>MongoDB</strong>
                  </label>
                  {draft.has_mongo && (
                    <div className="form-grid">
                      {fields([
                        { key: 'mongo_database', label: 'Database' },
                        { key: 'mongo_secret_ref', label: 'Connection secret reference' },
                      ])}
                    </div>
                  )}
                </div>
              </>
            )}
            {step === 3 && (
              <div className="preflight-results">
                {preflight.isPending ? (
                  <Loading />
                ) : preflight.error ? (
                  <>
                    <ErrorState error={preflight.error} />
                    <button type="button" className="button" onClick={() => preflight.mutate()}>
                      Run checks again
                    </button>
                  </>
                ) : preflight.data ? (
                  preflight.data.checks.map((check) => (
                    <div key={check.name}>
                      <CheckCircle2 size={21} />
                      <div>
                        <strong>{check.name}</strong>
                        <p>{check.message}</p>
                      </div>
                      <span>Passed</span>
                    </div>
                  ))
                ) : (
                  <button
                    type="button"
                    className="button primary"
                    onClick={() => preflight.mutate()}
                  >
                    Run pre-flight checks
                  </button>
                )}
              </div>
            )}
            {step === 4 && (
              <>
                <div className="review-card">
                  <div>
                    <span>Tenant</span>
                    <strong>{draft.display_name}</strong>
                    <code>{draft.tenant_id}</code>
                  </div>
                  <div>
                    <span>Sources</span>
                    <strong>
                      {[draft.has_mysql && 'MySQL', draft.has_mongo && 'MongoDB']
                        .filter(Boolean)
                        .join(' + ')}
                    </strong>
                  </div>
                  <div>
                    <span>Warehouse schema</span>
                    <code>{draft.warehouse_schema || draft.tenant_id}</code>
                  </div>
                  <div>
                    <span>Freshness SLA</span>
                    <strong>{draft.freshness_sla_min} minutes</strong>
                  </div>
                  <div>
                    <span>Initial load</span>
                    <strong>{draft.run_initial ? 'Start immediately' : 'Skip for now'}</strong>
                  </div>
                </div>
                <div className="notice info">
                  <ShieldCheck size={20} />
                  <p>
                    {runtime.mode === 'demo'
                      ? 'This demo creates local records and simulates Airbyte and Airflow steps. No external systems are contacted.'
                      : 'This workflow provisions Airbyte sources and connections through Airflow, using approved secret references.'}
                  </p>
                </div>
              </>
            )}
            <div className="wizard-actions">
              <button
                type="button"
                className="button"
                disabled={step === 1}
                onClick={() => set('step', String(step - 1))}
              >
                <ArrowLeft size={14} />
                Back
              </button>
              <button
                className="button primary"
                disabled={start.isPending || (step === 3 && !preflight.data?.passed)}
              >
                {step === 4 ? (
                  <>
                    <Rocket size={15} />
                    Start onboarding
                  </>
                ) : (
                  <>
                    Continue
                    <ArrowRight size={14} />
                  </>
                )}
              </button>
            </div>
          </form>
        </Panel>
      </div>
    </>
  );
}
