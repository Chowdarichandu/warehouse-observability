import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import {
  Empty,
  ErrorState,
  Loading,
  PageHeader,
  Pagination,
  Panel,
  Time,
  plural,
  useFilters,
} from '../components/ui';

export function DevMailbox() {
  const { page, set } = useFilters();
  const query = useQuery({
    queryKey: ['dev-mailbox', page],
    queryFn: () => api<Schema<'Page_DevMail_'>>(`/dev/mailbox?page=${page}`),
  });
  return (
    <>
      <PageHeader
        title="Dev mailbox"
        description="Account emails captured in demo mode instead of being sent: invites and password resets."
      />
      <Panel className={query.isPlaceholderData ? 'is-fetching' : ''}>
        {query.isPending ? (
          <Loading />
        ) : query.error ? (
          <ErrorState error={query.error} />
        ) : !query.data?.items.length ? (
          <Empty title="No captured email yet" />
        ) : (
          <>
            <ul className="mailbox-list">
              {query.data.items.map((mail) => (
                <li key={mail.id}>
                  <div className="mailbox-head">
                    <strong>{mail.subject}</strong>
                    <span className="muted">
                      To {mail.recipient} · <Time value={mail.created_at} relative />
                    </span>
                  </div>
                  <p className="mailbox-body">{mail.body}</p>
                </li>
              ))}
            </ul>
            <Pagination
              page={page}
              size={query.data.page_size}
              total={query.data.total}
              onChange={(next) => set('page', String(next))}
            />
            <p className="muted">{plural(query.data.total, 'captured email')}</p>
          </>
        )}
      </Panel>
    </>
  );
}
