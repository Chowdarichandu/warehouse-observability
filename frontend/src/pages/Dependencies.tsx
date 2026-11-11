import { useEffect, useMemo, useRef } from 'react';
import { Select } from '../components/Select';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, Database, GitBranch, Link2, Workflow } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, runPath } from '../api/client';
import type { Schema } from '../api/client';
import { StatusPill } from '../components/StatusPill';
import { Empty, ErrorState, Loading, PageHeader, Panel, Time, useFilters } from '../components/ui';
import './dependencies.css';

const stages = [
  ['source', 'Source systems'],
  ['dag', 'Airflow DAGs'],
  ['task', 'Airflow tasks'],
  ['connection', 'Airbyte connections'],
  ['warehouse', 'Warehouse schemas'],
  ['table', 'Observed tables'],
] as const;

export function Dependencies() {
  const { params, set } = useFilters();
  const [, setParams] = useSearchParams();
  const tenants = useQuery({
    queryKey: ['tenants', 1],
    queryFn: () => api<Schema<'Page_Tenant_'>>('/tenants?page=1&page_size=100'),
  });
  const tenant =
    params.get('tenant') ||
    localStorage.getItem('obs-dependencies-tenant') ||
    tenants.data?.items[0]?.tenant_id ||
    '';
  const graph = useQuery({
    queryKey: ['dependencies', tenant],
    queryFn: () =>
      api<Schema<'DependencyGraph'>>(`/dependencies?tenant_id=${encodeURIComponent(tenant)}`),
    enabled: Boolean(tenant),
  });
  const requestedNode = params.get('node');
  const selectedId = graph.data?.nodes.some((node) => node.id === requestedNode)
    ? requestedNode || ''
    : graph.data?.nodes[0]?.id || '';
  const selected = graph.data?.nodes.find((node) => node.id === selectedId);
  const detailsRef = useRef<HTMLDivElement>(null);
  // Clicking a node opens its details below the map; bring them into view so
  // the click visibly does something at any zoom level.
  useEffect(() => {
    if (requestedNode && detailsRef.current) {
      detailsRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [requestedNode]);
  const impact = useMemo(() => {
    const found = new Set<string>();
    const queue = selected ? [selected.id] : [];
    const adjacent = new Map<string, string[]>();
    for (const edge of graph.data?.edges || []) {
      const targets = adjacent.get(edge.source) || [];
      targets.push(edge.target);
      adjacent.set(edge.source, targets);
    }
    for (let index = 0; index < queue.length; index++) {
      for (const target of adjacent.get(queue[index]) || []) {
        if (!found.has(target) && target !== selected?.id) {
          found.add(target);
          queue.push(target);
        }
      }
    }
    return found;
  }, [graph.data, selected]);
  const layout = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    let count = 1;
    for (const [column, [kind]] of stages.entries()) {
      const nodes = graph.data?.nodes.filter((node) => node.kind === kind) || [];
      count = Math.max(count, nodes.length);
      nodes.forEach((node, index) =>
        positions.set(node.id, { x: column * 206 + 18, y: index * 78 + 62 }),
      );
    }
    return { positions, height: count * 78 + 86 };
  }, [graph.data]);
  const relationships =
    graph.data?.edges.filter((edge) => edge.source === selectedId || edge.target === selectedId) ||
    [];
  const affected = graph.data?.nodes.filter((node) => impact.has(node.id)) || [];
  const dagByTask = new Map<string, string>();
  if (graph.data) {
    const byId = new Map(graph.data.nodes.map((n) => [n.id, n]));
    for (const edge of graph.data.edges) {
      const source = byId.get(edge.source);
      const target = byId.get(edge.target);
      if (source?.kind === 'dag' && target?.kind === 'task') dagByTask.set(target.id, source.label);
    }
  }
  const DAG_LABELS: Record<string, string> = {
    mysql_cdc: 'MySQL CDC',
    mongo_cdc: 'MongoDB CDC',
    mysql_initial_load: 'MySQL initial load',
    mongo_initial_load: 'MongoDB initial load',
  };

  return (
    <>
      <PageHeader
        title="Pipeline dependencies"
        description="Configured and observed links between pipelines, and what a failure could affect."
        actions={
          <span className="tag">
            <GitBranch size={13} /> DEPENDENCY MAP
          </span>
        }
      />
      <div className="dependency-controls">
        <label htmlFor="dependency-tenant">Tenant</label>
        <Select
          id="dependency-tenant"
          value={tenant}
          onChange={(event) => {
            localStorage.setItem('obs-dependencies-tenant', event.target.value);
            const next = new URLSearchParams(params);
            next.set('tenant', event.target.value);
            next.delete('node');
            setParams(next);
          }}
        >
          {!tenants.data?.items.length && <option value="">Select a tenant</option>}
          {tenants.data?.items.map((item) => (
            <option key={item.tenant_id} value={item.tenant_id}>
              {item.display_name}
            </option>
          ))}
        </Select>
        <span className="dependency-legend">
          <i className="observed" /> Observed relationship
        </span>
        <span className="dependency-legend">
          <i /> Configured relationship
        </span>
      </div>
      {tenants.error ? (
        <ErrorState error={tenants.error} />
      ) : tenants.isPending ? (
        <Loading />
      ) : !tenant ? (
        <Empty title="No tenants configured">
          Add a tenant to start mapping its pipeline dependencies.
        </Empty>
      ) : graph.error ? (
        <ErrorState error={graph.error} />
      ) : graph.isPending ? (
        <Loading />
      ) : (
        <>
          <Panel
            title="Dependency map"
            subtitle="Select any node to inspect its evidence and potential downstream impact."
            className={graph.isPlaceholderData ? 'is-fetching' : ''}
          >
            {graph.data.truncated && (
              <div className="notice warning" role="status">
                This map reached its metadata limit. Select a tenant to narrow the map; some
                dependencies may be omitted.
              </div>
            )}
            {!graph.data.nodes.length ? (
              <Empty title="No dependency metadata yet">
                Configured connections and collected run or catalog metadata will appear here.
              </Empty>
            ) : (
              <div
                className="dependency-scroll"
                tabIndex={0}
                aria-label="Pipeline dependency graph; scroll horizontally to explore all stages"
              >
                <div className="dependency-canvas" style={{ height: layout.height }}>
                  {stages.map(([kind, label], column) => (
                    <div
                      className="dependency-stage"
                      style={{ left: column * 206 + 18 }}
                      key={kind}
                    >
                      {label}
                    </div>
                  ))}
                  <svg
                    className="dependency-lines"
                    width="1236"
                    height={layout.height}
                    aria-hidden="true"
                  >
                    <defs>
                      <marker
                        id="dependency-arrow"
                        markerWidth="7"
                        markerHeight="7"
                        refX="6"
                        refY="3.5"
                        orient="auto"
                      >
                        <path d="M0,0 L7,3.5 L0,7" fill="currentColor" />
                      </marker>
                    </defs>
                    {graph.data.edges.map((edge) => {
                      const from = layout.positions.get(edge.source);
                      const to = layout.positions.get(edge.target);
                      if (!from || !to) return null;
                      const forward = to.x >= from.x;
                      const x1 = from.x + (forward ? 172 : 0);
                      const x2 = to.x + (forward ? 0 : 172);
                      const bend = Math.max(30, Math.abs(x2 - x1) / 2);
                      const active = edge.source === selectedId || impact.has(edge.source);
                      return (
                        <path
                          key={edge.id}
                          className={`${edge.evidence} ${active ? 'active' : ''}`}
                          d={`M${x1},${from.y + 29} C${x1 + bend},${from.y + 29} ${x2 - bend},${to.y + 29} ${x2},${to.y + 29}`}
                          markerEnd="url(#dependency-arrow)"
                        />
                      );
                    })}
                  </svg>
                  {graph.data.nodes.map((node) => {
                    const position = layout.positions.get(node.id);
                    if (!position) return null;
                    return (
                      <button
                        key={node.id}
                        className={`dependency-node has-tip ${selectedId === node.id ? 'selected' : ''} ${impact.has(node.id) ? 'impacted' : ''}`}
                        style={{ left: position.x, top: position.y }}
                        aria-pressed={selectedId === node.id}
                        aria-label={`${node.kind}: ${node.label}`}
                        data-tip={`${node.kind} · ${node.label}`}
                        onClick={() => set('node', node.id)}
                      >
                        {node.kind === 'dag' || node.kind === 'task' ? (
                          <Workflow size={15} />
                        ) : node.kind === 'source' ||
                          node.kind === 'table' ||
                          node.kind === 'warehouse' ? (
                          <Database size={15} />
                        ) : (
                          <Link2 size={15} />
                        )}
                        <span>
                          <strong>{node.label}</strong>
                          <small>
                            {node.kind === 'task' && dagByTask.get(node.id)
                              ? `${DAG_LABELS[dagByTask.get(node.id) ?? ''] ?? dagByTask.get(node.id)} · `
                              : ''}
                            {node.status || node.evidence}
                          </small>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </Panel>
          <p className="dependency-note">{graph.data.note}</p>
          {selected && (
            <div className="dependency-details" ref={detailsRef}>
              <Panel
                title={selected.label}
                subtitle={`${selected.kind} · ${selected.evidence} metadata`}
              >
                <dl className="dependency-facts">
                  <div>
                    <dt>Last observed</dt>
                    <dd>
                      {selected.last_observed_at ? (
                        <Time value={selected.last_observed_at} relative />
                      ) : (
                        'Configuration only'
                      )}
                    </dd>
                  </div>
                  {selected.status && (
                    <div>
                      <dt>Latest linked run</dt>
                      <dd>
                        <StatusPill status={selected.status} />
                      </dd>
                    </div>
                  )}
                </dl>
                {selected.run_key && (
                  <Link className="button small" to={runPath(selected.run_key)}>
                    Investigate linked run <ArrowRight size={13} />
                  </Link>
                )}
                <h3 className="dependency-subheading">Relationship evidence</h3>
                {!relationships.length ? (
                  <p className="dependency-note">
                    No linked relationships have been collected for this node.
                  </p>
                ) : (
                  <ul className="dependency-evidence">
                    {relationships.map((edge) => (
                      <li key={edge.id}>
                        <span className={`dependency-evidence-kind ${edge.evidence}`}>
                          {edge.evidence}
                        </span>
                        <span>{edge.relationship}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
              <Panel
                title="Potential downstream impact"
                subtitle={`${affected.length} reachable assets. Routing indicates exposure, not a confirmed failure.`}
              >
                {!affected.length ? (
                  <p className="dependency-note">
                    No downstream dependencies are recorded for this node.
                  </p>
                ) : (
                  <ul className="dependency-impact">
                    {affected.map((node) => (
                      <li key={node.id}>
                        <button onClick={() => set('node', node.id)}>
                          <span>{node.label}</span>
                          <small>{node.kind}</small>
                          <ArrowRight size={13} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
          )}
        </>
      )}
    </>
  );
}
