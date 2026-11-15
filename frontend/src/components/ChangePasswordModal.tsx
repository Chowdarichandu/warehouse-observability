import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { api, ApiError } from '../api/client';
import type { Schema } from '../api/client';

export function ChangePasswordModal({
  onClose,
  notify,
}: {
  onClose: () => void;
  notify: (message: string) => void;
}) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const mutation = useMutation({
    mutationFn: () =>
      api<Schema<'Message'>>('/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ current_password: current, new_password: next }),
      }),
    onSuccess: () => {
      notify('Password changed. Use your new password the next time you sign in.');
      onClose();
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : 'Could not change the password.'),
  });
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    if (next.length < 8) return setError('New password must be at least 8 characters.');
    if (next !== confirm) return setError('New passwords do not match.');
    mutation.mutate();
  };
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Change password"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <strong>Change password</strong>
          <button className="icon-button" aria-label="Close" onClick={onClose}>
            <X size={16} />
          </button>
        </div>
        <form onSubmit={submit} className="modal-form">
          <label>
            Current password
            <input
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(event) => setCurrent(event.target.value)}
              required
            />
          </label>
          <label>
            New password
            <input
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
          </label>
          <label>
            Confirm new password
            <input
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <div className="modal-actions">
            <button type="button" className="button" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="button primary" disabled={mutation.isPending}>
              {mutation.isPending ? 'Changing…' : 'Change password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
