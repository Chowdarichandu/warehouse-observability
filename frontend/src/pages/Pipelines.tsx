import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  ArrowUpRight,
  Database,
  GitBranch,
  Layers3,
  Plus,
  Workflow,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { StatusPill } from '../components/StatusPill';
import { Empty, ErrorState, Loading, PageHeader, Panel, Time } from '../components/ui';
import './pipelines.css';

export function Pipelines() {
  const { can } = useApp();
  const query = useQuery({
    queryKey: ['pipeline-catalog'],
    queryFn: () => api<Schema<'PipelineCatalog'>>('/pipelines/catalog'),
  });
  if (query.isPending) return <Loading />;
  if (query.error) return <ErrorState error={query.error} />;
  const data = query.data;
  const card = (dag: Schema<'CatalogDag'>) => (
    <article className={`dag-card dag-${dag.source || 'coordinator'}`} key={dag.node_id}>
      <div className="dag-card-head">
        <span className="dag-icon">
          {dag.source ? <Database size={17} /> : <Workflow size={18} />}
        </span>
        <span className="dag-phase">{dag.phase}</span>
        {dag.latest_status ? (
          <StatusPill
            status={dag.latest_status}
            title={`${dag.label} (${dag.dag_id}) — last recorded ${
              dag.last_recorded_at
                ? new Date(dag.last_recorded_at).toLocaleString()
                : 'not recorded'
            } · ${dag.runs_24h} runs in 24h · ${dag.failures_24h} failures in 24h`}
          />
        ) : (
          <span
            className="dag-unobserved"
            title={`${dag.label} (${dag.dag_id}) — no run has been recorded for this DAG yet`}
          >
            Not yet observed
          </span>
        )}
      </div>
      <h3>{dag.label}</h3>
      <code>{dag.dag_id}</code>
      <p>
        {dag.node_id === 'coordinator'
          ? 'Validate the request, coordinate both source branches, and activate the tenant when every enabled branch is ready.'
          : dag.phase === 'Analytics'
            ? 'Available in the demo after the tenant’s MySQL initial load succeeds.'
            : dag.phase === 'Provision'
              ? 'Create the source and initial/CDC connections using approved secret references.'
              : dag.phase === 'Initial load'
                ? 'Complete the first warehouse load before CDC is allowed to start.'
                : 'Verify the first incremental sync, then continue through the recurring schedule.'}
      </p>
      <div className="dag-card-foot">
        <span>{dag.run_policy}</span>
        <span>{dag.runs_24h} runs · 24h</span>
      </div>
      <div className="dag-observed">
        {dag.last_recorded_at ? (
          <>
            Last recorded <Time value={dag.last_recorded_at} relative />
          </>
        ) : (
          'Waiting for execution evidence'
        )}
        {dag.failures_24h > 0 && <span className="danger-text">{dag.failures_24h} failed</span>}
      </div>
    </article>
  );
  return (
    <>
      <PageHeader
        title="Pipeline orchestration"
        eyebrow="WORKSPACE"
        description="Seven onboarding DAGs across two sources, followed by tenant-level analytics."
        actions={
          can('onboarding.start') && (
            <Link to="/onboarding" className="button primary">
              <Plus size={15} />
              Onboard tenant
            </Link>
          )
        }
      />
      <div className="catalog-intro">
        <div>
          <GitBranch size={19} />
          <strong>A deliberate sequence, with evidence at every handoff.</strong>
        </div>
        <span>
          {data.simulated
            ? 'Demo execution is simulated locally'
            : 'Configured Airflow orchestration'}
        </span>
      </div>
      <div className="coordinator-row">
        {data.dags.filter((d) => d.node_id === 'coordinator').map(card)}
        <div className="coordinator-explainer">
          <span className="eyebrow">THE READINESS RULE</span>
          <h2>
            Provision first.
            <br />
            Load once.
            <br />
            Verify CDC.
          </h2>
          <p>
            Each source follows its own dependencies. A failed step blocks its downstream work. The
            tenant stays in onboarding until every enabled source is ready.
          </p>
          <Link to="/onboarding" className="text-link">
            See the guided workflow
            <ArrowUpRight size={14} />
          </Link>
        </div>
      </div>
      {(['mysql', 'mongo'] as const).map((source) => (
        <section
          className={`source-branch branch-${source}`}
          key={source}
          aria-label={`${source === 'mysql' ? 'MySQL' : 'MongoDB'} orchestration branch`}
        >
          <div className="source-branch-heading">
            <span className="branch-label">
              <Database size={16} />
              {source === 'mysql' ? 'MySQL' : 'MongoDB'}
            </span>
            <span>Provisioning → Initial load → CDC</span>
          </div>
          <div className="dag-branch-grid">
            {data.dags.filter((d) => d.source === source).map(card)}
          </div>
        </section>
      ))}
      <section className="source-branch branch-analytics" aria-label="Analytics DAGs">
        <div className="source-branch-heading">
          <span className="branch-label">
            <Layers3 size={16} /> Analytics
          </span>
          <span>Available after a successful MySQL initial load</span>
        </div>
        <div className="dag-branch-grid">
          {data.dags.filter((d) => d.phase === 'Analytics').map(card)}
        </div>
      </section>
      <p className="catalog-note">
        <Layers3 size={15} />
        {data.note}
      </p>
      <Panel
        title="Tenant launches"
        subtitle="Resume an investigation where it left off. Progress is stored, so a page refresh does not restart the workflow."
      >
        {data.launches.length ? (
          <div className="launch-list">
            {data.launches.map((launch) => (
              <Link
                to={`/onboarding?tenant=${encodeURIComponent(launch.tenant_id)}`}
                className="launch-item"
                key={launch.tenant_id}
              >
                <span className="tenant-avatar">
                  {launch.display_name
                    .split(' ')
                    .map((w) => w[0])
                    .join('')
                    .slice(0, 2)}
                </span>
                <div>
                  <strong>{launch.display_name}</strong>
                  <span>
                    {launch.completed} of {launch.total} stages complete ·{' '}
                    <Time value={launch.updated_at} relative />
                  </span>
                </div>
                <StatusPill status={launch.state} />
                <ArrowRight size={16} />
              </Link>
            ))}
          </div>
        ) : (
          <Empty title="Your next tenant starts here">
            Launch System Engines from onboarding to follow provisioning, initial load, and CDC in
            one place.
          </Empty>
        )}
      </Panel>
    </>
  );
}
