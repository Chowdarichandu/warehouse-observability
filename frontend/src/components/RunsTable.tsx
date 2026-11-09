import { useMemo } from 'react';
import { flexRender, getCoreRowModel, useReactTable } from '@tanstack/react-table';
import type { ColumnDef } from '@tanstack/react-table';
import { Link } from 'react-router-dom';
import { ArrowUpDown, ExternalLink } from 'lucide-react';
import { runPath } from '../api/client';
import type { Schema } from '../api/client';
import { StatusPill } from './StatusPill';
import { Empty, NumberValue, Source, TenantLink, Time, formatDuration } from './ui';

export function RunsTable({
  runs,
  onSort,
}: {
  runs: Schema<'Run'>[];
  onSort?: (field: string) => void;
}) {
  const columns = useMemo<ColumnDef<Schema<'Run'>>[]>(
    () => [
      {
        accessorKey: 'status',
        header: 'Status',
        cell: ({ row }) => <StatusPill status={row.original.status} />,
      },
      {
        accessorKey: 'tenant_id',
        header: 'Tenant',
        cell: ({ row }) => <TenantLink id={row.original.tenant_id} />,
      },
      {
        accessorKey: 'source_type',
        header: 'Pipeline',
        cell: ({ row }) => (
          <span className="inline-flex">
            <Source source={row.original.source_type} />
            <span className="tag">{row.original.load_type}</span>
          </span>
        ),
      },
      {
        accessorKey: 'started_at',
        header: 'Started',
        cell: ({ row }) => <Time value={row.original.started_at} />,
      },
      {
        accessorKey: 'duration_s',
        header: 'Duration',
        cell: ({ row }) => (
          <span className="mono">
            {row.original.status === 'running'
              ? 'In progress'
              : formatDuration(row.original.duration_s)}
          </span>
        ),
      },
      {
        accessorKey: 'queue_delay_s',
        header: 'Queue',
        cell: ({ row }) => (
          <span className="mono">{formatDuration(row.original.queue_delay_s)}</span>
        ),
      },
      {
        accessorKey: 'rows_synced',
        header: 'Rows synced',
        cell: ({ row }) => <NumberValue value={row.original.rows_synced} />,
      },
      {
        id: 'detail',
        header: '',
        cell: ({ row }) => (
          <Link
            className="text-link"
            to={runPath(row.original.run_key)}
            aria-label={`Open ${row.original.status} run for ${row.original.tenant_id}`}
          >
            View run <ExternalLink size={12} />
          </Link>
        ),
      },
    ],
    [],
  );
  const table = useReactTable({ data: runs, columns, getCoreRowModel: getCoreRowModel() });
  if (!runs.length) return <Empty title="No runs match these filters" />;
  return (
    <div className="table-scroll">
      <table>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id}>
              {group.headers.map((header) => (
                <th key={header.id}>
                  {onSort &&
                  [
                    'status',
                    'tenant_id',
                    'started_at',
                    'duration_s',
                    'queue_delay_s',
                    'rows_synced',
                  ].includes(header.column.id) ? (
                    <button className="sort-button" onClick={() => onSort(header.column.id)}>
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <ArrowUpDown size={11} />
                    </button>
                  ) : (
                    flexRender(header.column.columnDef.header, header.getContext())
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
