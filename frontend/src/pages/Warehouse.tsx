import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Database, Rows3, Table2 } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { Empty, ErrorState, Loading, NumberValue, PageHeader, Panel, Time } from '../components/ui';

export function Warehouse() {
  const tenants = useQuery({
    queryKey: ['tenants', 1],
    queryFn: () => api<Schema<'Page_Tenant_'>>('/tenants?page=1&page_size=100'),
  });
  const [selected, setSelected] = useState('');
  const tenantId = selected || tenants.data?.items[0]?.tenant_id || '';
  const view = useQuery({
    queryKey: ['warehouse', tenantId],
    queryFn: () => api<Schema<'WarehouseView'>>(`/warehouse?tenant=${tenantId}`),
    enabled: Boolean(tenantId),
  });
  return (
    <>
      <PageHeader
        title="Warehouse"
        description="What has actually landed in the warehouse for each client — every table and the records it holds."
      />
      <Panel
        title="Warehouse contents"
        subtitle="Pick a client to see their tables and how many records have been loaded into each one."
        action={
          <select
            aria-label="Select client"
            value={tenantId}
            onChange={(e) => setSelected(e.target.value)}
          >
            {(tenants.data?.items ?? []).map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.display_name} ({t.tenant_id})
              </option>
            ))}
          </select>
        }
      >
        {view.isPending ? (
          <Loading />
        ) : view.error ? (
          <ErrorState error={view.error} />
        ) : !view.data || view.data.table_count === 0 ? (
          <Empty title="Nothing loaded yet">
            This client has no warehouse tables yet. Tables appear here after the first initial load
            completes.
          </Empty>
        ) : (
          <>
            <div className="kpi-grid">
              <div className="kpi-card">
                <div className="kpi-label">
                  <Table2 size={15} /> Tables loaded
                </div>
                <div className="kpi-value">
                  <NumberValue value={view.data.table_count} />
                </div>
                <div className="kpi-foot">Tables in this client’s warehouse schema</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">
                  <Rows3 size={15} /> Total records
                </div>
                <div className="kpi-value">
                  <NumberValue value={view.data.total_rows} />
                </div>
                <div className="kpi-foot">Records loaded across all tables</div>
              </div>
              <div className="kpi-card">
                <div className="kpi-label">
                  <Database size={15} /> Client schema
                </div>
                <div className="kpi-value schema-value">{view.data.tenant_id}</div>
                <div className="kpi-foot">One warehouse schema per client</div>
              </div>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Table</th>
                    <th>Records loaded</th>
                    <th>Last loaded</th>
                  </tr>
                </thead>
                <tbody>
                  {view.data.tables.map((table) => (
                    <tr key={table.table_name}>
                      <td>
                        <strong>{table.table_name}</strong>
                      </td>
                      <td>
                        <NumberValue value={table.row_count} />
                      </td>
                      <td>
                        <Time value={table.last_loaded_at} relative />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Panel>
    </>
  );
}
