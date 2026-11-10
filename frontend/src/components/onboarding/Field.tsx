import type { InputHTMLAttributes } from 'react';

export function Field({
  label,
  error,
  hint,
  id,
  ...input
}: {
  label: string;
  error?: string;
  hint?: string;
  id: string;
} & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <div className={`journey-field ${error ? 'is-invalid' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
        {...input}
      />
      {error ? (
        <p className="journey-field-error" id={`${id}-error`}>
          {error}
        </p>
      ) : hint ? (
        <p className="journey-field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}
