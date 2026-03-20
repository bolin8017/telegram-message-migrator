import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch, ApiError } from '../../src/api/client';

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('apiFetch', () => {
  it('returns parsed JSON on success', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 }),
    );
    const result = await apiFetch<{ status: string }>('/api/health');
    expect(result).toEqual({ status: 'ok' });
    expect(fetch).toHaveBeenCalledWith('/api/health', expect.objectContaining({
      credentials: 'include',
    }));
  });

  it('throws ApiError with detail on 4xx', async () => {
    expect.assertions(3);
    vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'Not authenticated' }), { status: 401 }),
      ),
    );
    await expect(apiFetch('/api/auth/status')).rejects.toThrow(ApiError);
    try {
      await apiFetch('/api/auth/status');
    } catch (e) {
      expect((e as ApiError).status).toBe(401);
      expect((e as ApiError).detail).toBe('Not authenticated');
    }
  });

  it('parses wait_seconds from 429 response', async () => {
    expect.assertions(2);
    vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: 'Rate limited', wait_seconds: 30 }), { status: 429 }),
      ),
    );
    try {
      await apiFetch('/api/auth/send-code/account_a');
    } catch (e) {
      expect((e as ApiError).status).toBe(429);
      expect((e as ApiError).waitSeconds).toBe(30);
    }
  });

  it('sends JSON body for POST requests', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'code_sent' }), { status: 200 }),
    );
    await apiFetch('/api/auth/send-code/account_a', {
      method: 'POST',
      body: JSON.stringify({ phone: '+1234567890' }),
    });
    expect(fetch).toHaveBeenCalledWith(
      '/api/auth/send-code/account_a',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }),
    );
  });

  it('returns undefined for 204 No Content', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    const result = await apiFetch('/api/user/data');
    expect(result).toBeUndefined();
  });

  it('falls back to statusText when response body is not JSON', async () => {
    expect.assertions(2);
    vi.spyOn(globalThis, 'fetch').mockImplementation(() =>
      Promise.resolve(
        new Response('Internal Server Error', {
          status: 500,
          statusText: 'Internal Server Error',
        }),
      ),
    );
    try {
      await apiFetch('/api/health');
    } catch (e) {
      expect((e as ApiError).status).toBe(500);
      expect((e as ApiError).detail).toBe('Internal Server Error');
    }
  });
});
