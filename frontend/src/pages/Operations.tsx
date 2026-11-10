import { useState } from 'react';
import { Select } from '../components/Select';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../api/client';
import type { Schema } from '../api/client';
import { useApp } from '../AppContext';
import { Empty, ErrorState, Loading, Panel, Time } from '../components/ui';

export function Operations() {
  const { notify } = useApp();
  const client = useQueryClient();
  const [review, setReview] = useState('');
  const operations = useQuery({
    queryKey: ['operations'],
    queryFn: () => api<Schema<'Page_Operation_'>>('/operations'),
  });
  const deliveries = useQuery({
    queryKey: ['deliveries'],
    queryFn: () => api<Schema<'Page_Delivery_'>>('/deliveries'),
  });
  const reconcile = useMutation({
    mutationFn: ({
      id,
      status,
      note,
    }: {
      id: string;
      status: 'succeeded' | 'failed';
      note: string;
    }) =>
      api<Schema<'Message'>>(`/operations/${id}/reconcile`, {
        method: 'POST',
        body: JSON.stringify({ status, note }),
      }),
    onSuccess: (result) => {
      notify(result.message);
      setReview('');
      void client.invalidateQueries({ queryKey: ['operations'] });
    },
    onError: (error) => notify(error.message),
  });
  return (
    <>
      <Panel
        title="Operations"
        subtitle="Upstream actions and their confirmed outcomes. Review unconfirmed actions in Airflow or Airbyte before another request."
      >
        {operations.isPending ? (
          <Loading />
        ) : operations.error ? (
          <ErrorState error={operations.error} />
        ) : !operations.data.items.length ? (
          <Empty title="No upstream operations yet">
            Live retries and onboarding requests appear here.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Requested</th>
                  <th>Action / target</th>
                  <th>Status</th>
                  <th>Details</th>
                </tr>
              </thead>
              <tbody>
                {operations.data.items.slice(0, 20).map((operation) => (
                  <tr key={operation.id}>
                    <td>
                      <Time value={operation.created_at} />
                    </td>
                    <td>
                      <strong>{operation.kind}</strong>
                      <br />
                      <small className="mono">{operation.target}</small>
                    </td>
                    <td>
                      <span className="tag">{operation.status}</span>
                    </td>
                    <td>
                      {operation.last_error && <p>{operation.last_error}</p>}
                      {['sending', 'uncertain', 'failed'].includes(operation.status) && (
                        <button
                          className="button small"
                          onClick={() => setReview(review === operation.id ? '' : operation.id)}
                        >
                          Review outcome
                        </button>
                      )}
                      {review === operation.id && (
                        <form
                          className="operation-review"
                          onSubmit={(event) => {
                            event.preventDefault();
                            const data = new FormData(event.currentTarget);
                            reconcile.mutate({
                              id: operation.id,
                              status: data.get('status') === 'succeeded' ? 'succeeded' : 'failed',
                              note: String(data.get('note')),
                            });
                          }}
                        >
                          <label>
                            Verified upstream outcome
                            <Select name="status">
                              <option value="succeeded">Accepted upstream</option>
                              <option value="failed">
                                Confirmed not accepted — allow a new request
                              </option>
                            </Select>
                          </label>
                          <label>
                            Evidence
                            <input
                              name="note"
                              minLength={10}
                              maxLength={1000}
                              placeholder="Upstream job ID or verification details"
                              required
                            />
                          </label>
                          <button className="button" disabled={reconcile.isPending}>
                            Save review
                          </button>
                        </form>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel
        title="Notification deliveries"
        subtitle="Queued, sent, retried, and failed deliveries. Disabled channels cancel queued messages."
      >
        {deliveries.isPending ? (
          <Loading />
        ) : deliveries.error ? (
          <ErrorState error={deliveries.error} />
        ) : !deliveries.data.items.length ? (
          <Empty title="No notifications yet">
            Configure a channel and send a test from Alerts.
          </Empty>
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Queued</th>
                  <th>Channel</th>
                  <th>Event</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Last error</th>
                </tr>
              </thead>
              <tbody>
                {deliveries.data.items.slice(0, 20).map((delivery) => (
                  <tr key={delivery.id}>
                    <td>
                      <Time value={delivery.at} />
                    </td>
                    <td>{delivery.channel_id}</td>
                    <td>{delivery.kind}</td>
                    <td>
                      <span className="tag">{delivery.status}</span>
                    </td>
                    <td>{delivery.attempts}</td>
                    <td>{delivery.last_error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
