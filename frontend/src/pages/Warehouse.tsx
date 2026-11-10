import { useState } from 'react';
import { Select } from '../components/Select';
import { useQuery } from '@tanstack/react-query';
import { Database, Rows3, Table2 } from 'lucide-react';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import {
  Empty,
  ErrorState,
  Loading,
  NumberValue,
  PageHeader,
  Panel,
  Time,
  useFilters,
} from '../components/ui';

export function Warehouse() {
  const { params, set } = useFilters();
  const tenants = useQuery({
    queryKey: ['tenants', 1],
    queryFn: () => api<Schema<'Page_Tenant_'>>('/tenants?page=1&page_size=100'),
  });
  const [pickedTable, setPickedTable] = useState('');
  const tenantId =
    params.get('tenant') ||
    localStorage.getItem('obs-warehouse-tenant') ||
    tenants.data?.items[0]?.tenant_id ||
    '';
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
        subtitle="Pick a client to see their tables and how many records have been loaded into each one. Live snapshot — it does not follow the global time range. Select a table row for its columns."
        className={view.isPlaceholderData ? 'is-fetching' : ''}
        action={
          <Select
            aria-label="Select client"
            value={tenantId}
            onChange={(e) => {
              setPickedTable('');
              localStorage.setItem('obs-warehouse-tenant', e.target.value);
              set('tenant', e.target.value);
            }}
          >
            {(tenants.data?.items ?? []).map((t) => (
              <option key={t.tenant_id} value={t.tenant_id}>
                {t.display_name} ({t.tenant_id})
              </option>
            ))}
          </Select>
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
                    <tr
                      key={table.table_name}
                      className={`row-clickable${
                        (pickedTable || view.data.tables[0]?.table_name) === table.table_name
                          ? ' row-selected'
                          : ''
                      }`}
                      onClick={() => setPickedTable(table.table_name)}
                    >
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
            {(() => {
              const table =
                view.data.tables.find((t) => t.table_name === pickedTable) ?? view.data.tables[0];
              if (!table) return null;
              return (
                <div className="alert-details">
                  <strong>{table.table_name}</strong>
                  <span className="muted">
                    {' '}
                    · <NumberValue value={table.row_count} /> records · last loaded{' '}
                    <Time value={table.last_loaded_at} relative />
                  </span>
                  {table.columns.length ? (
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Column</th>
                            <th>Type</th>
                          </tr>
                        </thead>
                        <tbody>
                          {table.columns.map((column) => (
                            <tr key={column.name}>
                              <td className="mono">{column.name}</td>
                              <td className="mono">{column.type}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="muted">No column snapshot recorded for this table yet.</p>
                  )}
                </div>
              );
            })()}
          </>
        )}
      </Panel>
    </>
  );
}
