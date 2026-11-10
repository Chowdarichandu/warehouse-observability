import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Database,
  GitBranch,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  Rocket,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { StatusPill } from '../components/StatusPill';
import { Loading } from '../components/ui';
import { Field } from '../components/onboarding/Field';
import { OnboardingProgress } from '../components/onboarding/Progress';
import { initialDraft, slugify, validateDraft } from '../components/onboarding/draft';
import type { DraftErrors, OnboardDraft } from '../components/onboarding/draft';
import './onboarding.css';

const STAGES = [
  { title: 'Tenant details', description: 'Identity, ownership & service level' },
  { title: 'Data sources', description: 'Connections & secret references' },
  { title: 'Pre-flight checks', description: 'Connectivity & CDC readiness' },
  { title: 'Review & start', description: 'Your seven-DAG activation plan' },
];
export function Onboarding() {
  const { runtime, can, access, notify } = useApp();
  const canStart = can('onboarding.start');
  const canRead = can('workspace.read');
  const [params, setParams] = useSearchParams();
  const tenant = params.get('tenant') || '';
  const requested = Number(params.get('step') || 1);
  const [draft, setDraft] = useState<OnboardDraft>(() => initialDraft(runtime.mode));
  const [errors, setErrors] = useState<DraftErrors>({});
  const [detailsValid, setDetailsValid] = useState(false);
  const [sourcesValid, setSourcesValid] = useState(false);
  const [checkedFingerprint, setCheckedFingerprint] = useState<string | null>(null);
  const [slugEdited, setSlugEdited] = useState(
    () => draft.tenant_id !== slugify(draft.display_name),
  );
  const fingerprint = JSON.stringify(draft);
  const generation = useRef(0);
  const currentFingerprint = useRef(fingerprint);
  currentFingerprint.current = fingerprint;
  const preflight = useMutation({
    mutationFn: (request: { input: OnboardDraft; generation: number }) =>
      api<Schema<'Preflight'>>('/onboarding/preflight', {
        method: 'POST',
        body: JSON.stringify(request.input),
      }),
    onSuccess: (result, request) => {
      if (
        request.generation === generation.current &&
        JSON.stringify(request.input) === currentFingerprint.current
      )
        setCheckedFingerprint(
          result.passed && result.checks.length > 0 && result.checks.every((check) => check.passed)
            ? JSON.stringify(request.input)
            : null,
        );
    },
    onError: (e) => notify(e.message),
  });
  const readiness = checkedFingerprint === fingerprint && preflight.data?.passed === true;
  const checkConfiguration = () =>
    preflight.mutate({ input: { ...draft }, generation: generation.current });
  const maxStep = !detailsValid ? 1 : !sourcesValid ? 2 : readiness ? 4 : 3;
  const step = Number.isInteger(requested) ? Math.max(1, Math.min(maxStep, requested)) : 1;
  useEffect(() => {
    if (!tenant && requested !== step)
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous);
          next.set('step', String(step));
          return next;
        },
        { replace: true },
      );
  }, [tenant, requested, step, setParams]);
  const resetPreflight = preflight.reset;
  const previousStep = useRef(step);
  useEffect(() => {
    if (step < previousStep.current) {
      generation.current += 1;
      setCheckedFingerprint(null);
      resetPreflight();
    }
    previousStep.current = step;
  }, [step, resetPreflight]);
  const start = useMutation({
    mutationFn: () =>
      api<Schema<'OnboardProgress'>>('/onboarding', {
        method: 'POST',
        body: JSON.stringify(draft),
      }),
    onSuccess: (result) => {
      setParams({ tenant: result.tenant_id });
      try {
        sessionStorage.removeItem(`obs-onboard-draft-v2-${runtime.mode}`);
      } catch {
        /* Browser privacy settings can disable draft storage. */
      }
    },
    onError: (e) => notify(e.message),
  });
  function persist(next: OnboardDraft) {
    setDraft(next);
    try {
      sessionStorage.setItem(`obs-onboard-draft-v2-${runtime.mode}`, JSON.stringify(next));
    } catch {
      /* The current in-memory draft remains available. */
    }
    generation.current += 1;
    setCheckedFingerprint(null);
    preflight.reset();
    start.reset();
  }
  function update<K extends keyof OnboardDraft>(key: K, value: OnboardDraft[K]) {
    let next = { ...draft, [key]: value };
    if (key === 'display_name' && !slugEdited) {
      const slug = slugify(String(value));
      next = {
        ...next,
        tenant_id: slug,
        warehouse_schema:
          draft.warehouse_schema === draft.tenant_id ? slug : draft.warehouse_schema,
      };
    }
    if (key === 'tenant_id') {
      setSlugEdited(true);
      if (draft.warehouse_schema === draft.tenant_id) next.warehouse_schema = String(value);
    }
    persist(next);
    setErrors((previous) => ({ ...previous, [key]: undefined, sources: undefined }));
  }
  function go(value: number) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      next.set('step', String(value));
      next.delete('tenant');
      return next;
    });
  }
  function back(value: number) {
    generation.current += 1;
    setCheckedFingerprint(null);
    preflight.reset();
    start.reset();
    setErrors({});
    if (value <= 1) {
      setDetailsValid(false);
      setSourcesValid(false);
    } else if (value <= 2) setSourcesValid(false);
    go(value);
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === 1 || step === 2) {
      const found = validateDraft(draft, step, runtime.mode);
      setErrors(found);
      if (Object.values(found).some(Boolean)) {
        requestAnimationFrame(() =>
          document.querySelector<HTMLInputElement>('.journey-field [aria-invalid="true"]')?.focus(),
        );
        return;
      }
      if (step === 1) {
        setDetailsValid(true);
        go(2);
      } else {
        setSourcesValid(true);
        go(3);
        checkConfiguration();
      }
    } else if (step === 3) {
      if (readiness) go(4);
    } else if (readiness && canStart) start.mutate();
  }
  function textField(
    key: keyof OnboardDraft,
    label: string,
    options: { hint?: string; type?: string; min?: number; max?: number; maxLength?: number } = {},
  ) {
    return (
      <Field
        id={`onboard-${key}`}
        label={label}
        error={errors[key]}
        value={String(draft[key] ?? '')}
        onChange={(event) =>
          update(key, options.type === 'number' ? Number(event.target.value) : event.target.value)
        }
        {...options}
      />
    );
  }
  if (!access) return <Loading />;
  if (tenant && canRead) return <OnboardingProgress tenant={tenant} />;
  if (!canStart || !canRead) {
    const permission = access?.permissions.find((item) => item.id === 'onboarding.start');
    return (
      <div className="tenant-journey">
        <div className="journey-access">
          <LockKeyhole size={28} />
          <h1>Onboarding access required</h1>
          <p>
            {permission?.reason ||
              'Your current access allows tenant investigation. An operator or administrator with onboarding enabled can configure and activate tenants.'}
          </p>
          <Link className="button" to="/tenants">
            Open tenants <ArrowRight size={14} />
          </Link>
        </div>
      </div>
    );
  }
  const selectedSources = [draft.has_mysql && 'MySQL', draft.has_mongo && 'MongoDB'].filter(
    Boolean,
  );
  return (
    <div className="tenant-journey">
      <div className="journey-page-top">
        <Link className="journey-back-link" to="/tenants">
          <ArrowLeft size={15} />
          All tenants
        </Link>
        <span className="journey-top-context">WORKSPACE / NEW TENANT</span>
      </div>
      <header className="journey-intro">
        <div>
          <span className="journey-eyebrow">A CLEAR PATH TO YOUR FIRST SYNC</span>
          <h1>Onboard a tenant</h1>
          <p>Connect your sources, verify readiness, and follow every stage of onboarding.</p>
        </div>
        <span className="journey-security-pill">
          <ShieldCheck size={15} />
          Secret references only
        </span>
      </header>
      {runtime.mode === 'live' && (
        <div className="journey-check-failure" role="alert">
          <TriangleAlert size={20} />
          <p>
            Live onboarding is unavailable until tenant isolation and DAG recovery have been
            validated in staging. You can review the configuration, but cannot start a workflow.
          </p>
        </div>
      )}
      <div className="journey-shell">
        <aside className="journey-rail">
          <nav aria-label="Onboarding steps">
            <ol>
              {STAGES.map((stage, index) => (
                <li
                  className={
                    step === index + 1 ? 'is-active' : step > index + 1 ? 'is-done' : 'is-upcoming'
                  }
                  key={stage.title}
                >
                  <button
                    type="button"
                    disabled={index + 1 > step}
                    onClick={() => {
                      if (index + 1 < step) back(index + 1);
                    }}
                    aria-current={step === index + 1 ? 'step' : undefined}
                  >
                    <span className="journey-step-number">
                      {step > index + 1 ? <Check size={15} /> : String(index + 1).padStart(2, '0')}
                    </span>
                    <span>
                      <strong>{stage.title}</strong>
                      <small>{stage.description}</small>
                    </span>
                    {step === index + 1 && <ChevronRight size={14} />}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
          <div className="journey-rail-note">
            <KeyRound size={20} />
            <h2>Your credentials stay in your vault.</h2>
            <p>
              We use approved secret references to resolve connections. Passwords never belong in
              this form.
            </p>
          </div>
          <div className="journey-rail-footer">
            <GitBranch size={15} />
            <span>1 coordinator · 6 source DAGs</span>
          </div>
        </aside>
        <section className="journey-canvas">
          <form onSubmit={submit} noValidate>
            <div className="journey-stage-heading">
              <div>
                <span className="journey-eyebrow">STEP {String(step).padStart(2, '0')} / 04</span>
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
                      'Give the workspace an identity, an owner and a clear freshness target.',
                      'Choose the sources to connect. Each gets its own provisioning, initial-load and CDC pipeline.',
                      runtime.mode === 'demo'
                        ? 'Validate this configuration using simulated connectivity and CDC checks.'
                        : 'Confirm source permissions, replication settings and the destination schema before provisioning.',
                      'Review the configuration and activation order before starting.',
                    ][step - 1]
                  }
                </p>
              </div>
              <span className="journey-stage-index">{String(step).padStart(2, '0')}</span>
            </div>
            <div className="journey-stage-content">
              {step === 1 && (
                <>
                  <div className="journey-identity-preview">
                    <span>
                      {(draft.display_name || 'New tenant')
                        .split(' ')
                        .map((word) => word[0])
                        .slice(0, 2)
                        .join('')
                        .toUpperCase()}
                    </span>
                    <div>
                      <strong>{draft.display_name || 'Your new tenant'}</strong>
                      <code>{draft.tenant_id || 'tenant_slug'}</code>
                    </div>
                    <span className="journey-draft-label">DRAFT</span>
                  </div>
                  <div className="journey-form-grid">
                    {textField('display_name', 'Display name', {
                      hint: 'The name your team will see across the console.',
                      maxLength: 100,
                    })}
                    {textField('tenant_id', 'Tenant slug', {
                      hint: 'A permanent identifier used for connections and pipeline mapping.',
                      maxLength: 48,
                    })}
                    {textField('owner_email', 'Owner email', {
                      type: 'email',
                      hint: 'The person responsible for this tenant’s data.',
                      maxLength: 254,
                    })}
                    {textField('warehouse_schema', 'Warehouse schema', {
                      hint:
                        runtime.mode === 'live'
                          ? 'This schema must already exist in the destination.'
                          : 'Defaults to the tenant slug.',
                      maxLength: 63,
                    })}
                    {textField('freshness_sla_min', 'Freshness SLA (minutes)', {
                      type: 'number',
                      min: 5,
                      max: 10080,
                      hint: 'Alert when data is older than this target.',
                    })}
                  </div>
                  <div className="journey-form-divider" />
                  <label className="journey-choice">
                    <input
                      type="checkbox"
                      checked={draft.run_initial}
                      onChange={(event) => update('run_initial', event.target.checked)}
                    />
                    <span>
                      <strong>Run initial loads after provisioning</strong>
                      <small>
                        {draft.run_initial
                          ? 'Take the first snapshot, then enable CDC after it succeeds.'
                          : 'Provision connections now. Initial loads and CDC will wait for an explicit start.'}
                      </small>
                    </span>
                  </label>
                </>
              )}
              {step === 2 && (
                <>
                  <div className="journey-source-cards">
                    {(['mysql', 'mongo'] as const).map((source) => {
                      const enabled = source === 'mysql' ? draft.has_mysql : draft.has_mongo;
                      return (
                        <div
                          className={`journey-source-card ${enabled ? 'is-enabled' : ''}`}
                          key={source}
                        >
                          <header>
                            <span className={`journey-source-icon ${source}`}>
                              <Database size={20} />
                            </span>
                            <div>
                              <h3>
                                {source === 'mysql'
                                  ? 'MySQL · tenant database'
                                  : 'MongoDB · shared cluster'}
                              </h3>
                              <p>
                                {source === 'mysql'
                                  ? 'A dedicated database for this tenant'
                                  : 'Shared cluster · tenant_id identifies each tenant’s documents'}
                              </p>
                            </div>
                            <label className="journey-source-toggle">
                              <input
                                type="checkbox"
                                checked={enabled}
                                onChange={(event) =>
                                  update(
                                    source === 'mysql' ? 'has_mysql' : 'has_mongo',
                                    event.target.checked,
                                  )
                                }
                              />
                              <span>Enable {source === 'mysql' ? 'MySQL' : 'MongoDB'}</span>
                            </label>
                          </header>
                          {enabled ? (
                            <div className="journey-form-grid">
                              {source === 'mysql' ? (
                                <>
                                  {textField('mysql_host', 'MySQL host', { maxLength: 254 })}
                                  {textField('mysql_port', 'MySQL port', {
                                    type: 'number',
                                    min: 1,
                                    max: 65535,
                                  })}
                                  {textField('mysql_database', 'MySQL database', {
                                    maxLength: 100,
                                  })}
                                  {textField('mysql_user', 'Replication user', { maxLength: 100 })}
                                  <div className="journey-full-width">
                                    {textField('mysql_secret_ref', 'MySQL secret reference', {
                                      hint:
                                        runtime.mode === 'live'
                                          ? 'An AWS Secrets Manager reference containing the reviewed source credentials.'
                                          : 'For this demo, use a demo:// secret reference.',
                                    })}
                                  </div>
                                </>
                              ) : (
                                <>
                                  {textField('mongo_database', 'Shared MongoDB database', {
                                    maxLength: 100,
                                  })}
                                  {textField('mongo_secret_ref', 'MongoDB secret reference', {
                                    hint: 'Reference the connection URI stored in your secret manager.',
                                  })}
                                </>
                              )}
                            </div>
                          ) : (
                            <p className="journey-source-disabled">
                              This branch will be marked skipped in the activation workflow.
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {errors.sources && (
                    <p className="journey-field-error" role="alert">
                      {errors.sources}
                    </p>
                  )}
                  <div className="journey-inline-note">
                    <KeyRound size={16} />
                    <p>
                      Enter references, never passwords or connection strings with embedded
                      credentials.
                    </p>
                  </div>
                </>
              )}
              {step === 3 && (
                <div className="journey-preflight">
                  {preflight.isPending ? (
                    <div className="journey-checking" role="status">
                      <LoaderCircle size={27} className="journey-spin" />
                      <h3>Checking your configuration</h3>
                      <p>
                        Validating connectivity, replication settings and access for the selected
                        sources.
                      </p>
                    </div>
                  ) : preflight.error ? (
                    <div className="journey-check-failure" role="alert">
                      <TriangleAlert size={22} />
                      <div>
                        <h3>We could not complete the checks</h3>
                        <p>{preflight.error.message}</p>
                        <button
                          type="button"
                          className="button"
                          onClick={() => checkConfiguration()}
                        >
                          Run checks again
                        </button>
                      </div>
                    </div>
                  ) : preflight.data ? (
                    <>
                      <div
                        className={`journey-check-summary ${readiness ? 'is-passed' : 'is-failed'}`}
                      >
                        {readiness ? <CheckCircle2 size={23} /> : <TriangleAlert size={23} />}
                        <div>
                          <h3>
                            {readiness
                              ? 'Your configuration is ready'
                              : 'Resolve the failed checks to continue'}
                          </h3>
                          <p>
                            {preflight.data.checks.filter((check) => check.passed).length} of{' '}
                            {preflight.data.checks.length} checks passed
                            {preflight.data.simulated ? ' · simulated evidence' : ''}
                          </p>
                        </div>
                        <button
                          type="button"
                          className="button small"
                          onClick={() => {
                            setCheckedFingerprint(null);
                            checkConfiguration();
                          }}
                        >
                          Check again
                        </button>
                      </div>
                      <ul className="journey-check-list">
                        {preflight.data.checks.map((check) => (
                          <li key={check.name} className={check.passed ? 'is-passed' : 'is-failed'}>
                            {check.passed ? (
                              <CheckCircle2 size={19} />
                            ) : (
                              <TriangleAlert size={19} />
                            )}
                            <div>
                              <strong>{check.name}</strong>
                              <p>{check.message}</p>
                            </div>
                            <span>{check.passed ? 'Passed' : 'Failed'}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <div className="journey-checking">
                      <ShieldCheck size={28} />
                      <h3>Verify this configuration</h3>
                      <p>
                        Configuration changes invalidate previous results. Run the checks again
                        before reviewing.
                      </p>
                      <button
                        type="button"
                        className="button primary"
                        onClick={() => checkConfiguration()}
                      >
                        Run pre-flight checks
                      </button>
                    </div>
                  )}
                </div>
              )}
              {step === 4 && (
                <>
                  <div className="journey-review-identity">
                    <span className="journey-review-avatar">
                      {draft.display_name
                        .split(' ')
                        .map((word) => word[0])
                        .slice(0, 2)
                        .join('')
                        .toUpperCase()}
                    </span>
                    <div>
                      <h3>{draft.display_name}</h3>
                      <code>{draft.tenant_id}</code>
                    </div>
                    <span className="journey-review-ready">
                      <CheckCircle2 size={15} />
                      Checks passed
                    </span>
                  </div>
                  <dl className="journey-review-details">
                    <div>
                      <dt>Owner</dt>
                      <dd>{draft.owner_email}</dd>
                    </div>
                    <div>
                      <dt>Destination schema</dt>
                      <dd>
                        <code>{draft.warehouse_schema || draft.tenant_id}</code>
                      </dd>
                    </div>
                    <div>
                      <dt>Freshness target</dt>
                      <dd>{draft.freshness_sla_min} minutes</dd>
                    </div>
                    <div>
                      <dt>Initial load</dt>
                      <dd>
                        {draft.run_initial ? 'Start after provisioning' : 'Wait for explicit start'}
                      </dd>
                    </div>
                  </dl>
                  <div className="journey-review-plan">
                    <div className="journey-section-heading">
                      <div>
                        <span className="journey-eyebrow">YOUR ACTIVATION PLAN</span>
                        <h3>One coordinator, independent source branches</h3>
                      </div>
                      <GitBranch size={20} />
                    </div>
                    <div className="journey-plan-coordinator">
                      <GitBranch size={16} />
                      <strong>Onboarding coordinator</strong>
                      <span>Routes & tracks every stage</span>
                    </div>
                    {(['mysql', 'mongo'] as const).map((source) => {
                      const selected = source === 'mysql' ? draft.has_mysql : draft.has_mongo;
                      return (
                        <div
                          className={`journey-plan-branch ${selected ? '' : 'is-skipped'}`}
                          key={source}
                        >
                          <span>
                            <Database size={15} />
                            {source === 'mysql' ? 'MySQL' : 'MongoDB'}
                          </span>
                          <div>
                            <strong>Provision</strong>
                            <ArrowRight size={12} />
                            <strong>Initial load</strong>
                            <ArrowRight size={12} />
                            <strong>CDC</strong>
                          </div>
                          <small>
                            {selected
                              ? draft.run_initial
                                ? 'After initial success'
                                : 'Initial & CDC wait'
                              : 'Skipped'}
                          </small>
                        </div>
                      );
                    })}
                  </div>
                  <div className="journey-inline-note">
                    <ShieldCheck size={17} />
                    <p>
                      {runtime.mode === 'demo'
                        ? 'This demonstration writes local records and simulates execution. External sources and AWS are not contacted.'
                        : 'Live execution is unavailable until tenant isolation and DAG recovery have been validated in staging.'}
                    </p>
                  </div>
                </>
              )}
              {start.error && (
                <div className="journey-check-failure" role="alert">
                  <TriangleAlert size={20} />
                  <p>{start.error.message}</p>
                </div>
              )}
            </div>
            <footer className="journey-actions">
              <button
                type="button"
                className="button"
                disabled={step === 1 || start.isPending || preflight.isPending}
                onClick={() => back(step - 1)}
              >
                <ArrowLeft size={14} />
                Back
              </button>
              <span>
                {step === 1
                  ? 'Your draft is saved in this browser'
                  : step === 2
                    ? `${selectedSources.length} source${selectedSources.length === 1 ? '' : 's'} selected`
                    : step === 3
                      ? readiness
                        ? 'Ready to review'
                        : 'Verification required'
                      : draft.run_initial
                        ? 'Initial loads will run after provisioning'
                        : 'Initial loads will remain on hold'}
              </span>
              <button
                className="button primary"
                disabled={
                  start.isPending ||
                  preflight.isPending ||
                  (step >= 3 && !readiness) ||
                  (step === 4 && runtime.mode === 'live')
                }
              >
                {step === 4 ? (
                  <>
                    {start.isPending ? (
                      <LoaderCircle size={15} className="journey-spin" />
                    ) : (
                      <Rocket size={15} />
                    )}{' '}
                    {start.isPending ? 'Starting workflow…' : 'Start onboarding'}
                  </>
                ) : (
                  <>
                    Continue <ArrowRight size={14} />
                  </>
                )}
              </button>
            </footer>
          </form>
        </section>
      </div>
      <div className="journey-bottom-note">
        <LockKeyhole size={13} />
        <span>Every provisioning request is role-checked and recorded in your audit trail.</span>
        <StatusPill status="configured" />
      </div>
    </div>
  );
}
