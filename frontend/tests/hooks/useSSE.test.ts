import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useSSE } from '../../src/hooks/useSSE';

// Mock EventSource
class MockEventSource {
  static instances: MockEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners: Record<string, ((e: unknown) => void)[]> = {};
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(event: string, handler: (e: unknown) => void) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event]!.push(handler);
  }

  close() {
    this.closed = true;
  }

  // Test helper: simulate an event
  _emit(event: string, data: string) {
    const handlers = this.listeners[event];
    if (handlers) {
      for (const handler of handlers) {
        handler({ data } as unknown);
      }
    }
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal('EventSource', MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('useSSE', () => {
  it('creates EventSource with correct URL', () => {
    renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: { progress: vi.fn() },
      }),
    );

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0]!.url).toBe('/api/transfer/progress');
  });

  it('does not create EventSource when url is null', () => {
    renderHook(() =>
      useSSE({
        url: null,
        events: { progress: vi.fn() },
      }),
    );

    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('closes EventSource on unmount', () => {
    const { unmount } = renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: { progress: vi.fn() },
      }),
    );

    const es = MockEventSource.instances[0]!;
    expect(es.closed).toBe(false);
    unmount();
    expect(es.closed).toBe(true);
  });

  it('registers event listeners for each event name', () => {
    renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: {
          progress: vi.fn(),
          status: vi.fn(),
        },
      }),
    );

    const es = MockEventSource.instances[0]!;
    expect(es.listeners['progress']).toHaveLength(1);
    expect(es.listeners['status']).toHaveLength(1);
  });

  it('parses JSON data and calls handler', () => {
    const handler = vi.fn();
    renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: { progress: handler },
      }),
    );

    const es = MockEventSource.instances[0]!;
    es._emit('progress', JSON.stringify({ percent: 42 }));
    expect(handler).toHaveBeenCalledWith({ percent: 42 });
  });

  it('passes raw string when JSON parse fails', () => {
    const handler = vi.fn();
    renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: { progress: handler },
      }),
    );

    const es = MockEventSource.instances[0]!;
    es._emit('progress', 'not-json');
    expect(handler).toHaveBeenCalledWith('not-json');
  });

  it('calls onOpen when EventSource connects', () => {
    const onOpen = vi.fn();
    renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: { progress: vi.fn() },
        onOpen,
      }),
    );

    const es = MockEventSource.instances[0]!;
    es.onopen?.();
    expect(onOpen).toHaveBeenCalled();
  });

  it('calls onError when EventSource errors', () => {
    const onError = vi.fn();
    renderHook(() =>
      useSSE({
        url: '/api/transfer/progress',
        events: { progress: vi.fn() },
        onError,
      }),
    );

    const es = MockEventSource.instances[0]!;
    es.onerror?.();
    expect(onError).toHaveBeenCalled();
  });

  it('recreates EventSource when URL changes', () => {
    const { rerender } = renderHook(
      ({ url }: { url: string | null }) =>
        useSSE({ url, events: { progress: vi.fn() } }),
      { initialProps: { url: '/api/v1' as string | null } },
    );

    expect(MockEventSource.instances).toHaveLength(1);
    const first = MockEventSource.instances[0]!;

    rerender({ url: '/api/v2' });
    expect(first.closed).toBe(true);
    expect(MockEventSource.instances).toHaveLength(2);
    expect(MockEventSource.instances[1]!.url).toBe('/api/v2');
  });
});
