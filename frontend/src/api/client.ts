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
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);
  const abort = () => controller.abort();
  const parent = init?.signal;
  if (parent?.aborted) controller.abort();
  parent?.addEventListener('abort', abort, { once: true });
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  headers.set('X-CSRF-Token', csrf);
  try {
    const response = await fetch(`/api${path}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      ...init,
      signal: controller.signal,
      headers,
    });
    // Proxies and cold starts can return HTML or an empty response. Avoid surfacing
    // browser-specific JSON parser errors (especially Safari's opaque SyntaxError).
    let body;
    try {
      body = await response.json();
    } catch {
      throw new ApiError(
        response.status || 502,
        'The console service returned an unexpected response. Please try again shortly.',
      );
    }
    if (!response.ok) {
      throw new ApiError(
        response.status,
        typeof body?.error?.message === 'string'
          ? body.error.message
          : 'The request failed. Please try again.',
      );
    }
    if (body === null || typeof body !== 'object') {
      throw new ApiError(
        502,
        'The console service returned an unexpected response. Please try again shortly.',
      );
    }
    return body as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      0,
      controller.signal.aborted
        ? 'The request timed out or was cancelled. Please try again.'
        : 'Unable to reach the console service. Check your connection and try again.',
    );
  } finally {
    clearTimeout(timeout);
    parent?.removeEventListener('abort', abort);
  }
}
export function queryString(params: Record<string, string | number | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value !== undefined && value !== '') query.set(key, String(value));
  return query.toString();
}
export const runPath = (key: string) => `/runs/${encodeURIComponent(key)}`;
