import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, setCsrf } from './client';

afterEach(() => {
  vi.unstubAllGlobals();
  setCsrf('');
});

describe('API transport', () => {
  it('preserves custom Headers and sends same-origin session and CSRF', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"status":"ok"}'));
    vi.stubGlobal('fetch', fetcher);
    setCsrf('fixture-csrf');
    expect(await api('/health', { headers: new Headers({ 'X-Test': 'yes' }) })).toEqual({
      status: 'ok',
    });
    const [url, init] = fetcher.mock.calls[0];
    expect(url).toBe('/api/health');
    expect(init.headers.get('X-CSRF-Token')).toBe('fixture-csrf');
    expect(init.headers.get('X-Test')).toBe('yes');
    expect(init.credentials).toBe('same-origin');
    expect(init.cache).toBe('no-store');
  });
  it('preserves unauthorized status even when a proxy returns a non-JSON body', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })));
    await expect(api('/me')).rejects.toMatchObject({ status: 401 });
  });
  it.each(['<!doctype html><h1>Gateway unavailable</h1>', '', '"unexpected scalar"', 'null'])(
    'normalizes invalid successful responses for every browser: %s',
    async (body) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body)));
      await expect(api('/config')).rejects.toThrow(
        'The console service returned an unexpected response.',
      );
    },
  );
  it('keeps structured API failures actionable', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('{"error":{"message":"Please sign in."}}', { status: 401 }),
        ),
    );
    await expect(api('/me')).rejects.toMatchObject({ status: 401, message: 'Please sign in.' });
  });
  it('normalizes browser-specific fetch errors without reflecting internal details', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockRejectedValue(
          new DOMException('The string did not match the expected pattern.', 'SyntaxError'),
        ),
    );
    await expect(api('/config')).rejects.toEqual(
      new ApiError(0, 'Unable to reach the console service. Check your connection and try again.'),
    );
  });
  it('propagates caller cancellation', async () => {
    const controller = new AbortController();
    controller.abort();
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url, init) => {
        expect(init.signal.aborted).toBe(true);
        return Promise.reject(new DOMException('', 'AbortError'));
      }),
    );
    await expect(api('/health', { signal: controller.signal })).rejects.toThrow(
      'timed out or was cancelled',
    );
  });
});
