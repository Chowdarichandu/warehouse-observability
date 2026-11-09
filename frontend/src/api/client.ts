import type { components } from './generated';

export type Schema<K extends keyof components['schemas']> = components['schemas'][K];
let csrf = '';
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf, ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      body.error?.message || 'The request failed. Please try again.',
    );
  }
  return response.json() as Promise<T>;
}
export function queryString(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== '') query.set(key, String(value));
  return query.toString();
}
export const runPath = (key: string) => `/runs/${encodeURIComponent(key)}`;
