import { useEffect, useRef } from 'react';

interface UseSSEOptions {
  url: string | null;
  events: Record<string, (data: unknown) => void>;
  onError?: (retriesExhausted: boolean) => void;
  onOpen?: () => void;
}

const MAX_BACKOFF = 30_000;
const MAX_RETRIES = 10;

export function useSSE({ url, events, onError, onOpen }: UseSSEOptions) {
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;

  useEffect(() => {
    if (!url) return;

    let backoff = 1000;
    let retries = 0;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let es: EventSource | null = null;
    let disposed = false;

    function connect() {
      if (disposed) return;

      es = new EventSource(url!, { withCredentials: true });

      es.onopen = () => {
        backoff = 1000;
        retries = 0;
        onOpenRef.current?.();
      };

      es.onerror = () => {
        es?.close();
        es = null;
        if (!disposed && retries < MAX_RETRIES) {
          retries++;
          onErrorRef.current?.(false);
          retryTimer = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, MAX_BACKOFF);
        } else if (!disposed) {
          console.error(`[useSSE] Retries exhausted (${MAX_RETRIES}) for ${url}`);
          onErrorRef.current?.(true);
        }
      };

      // Read from ref at dispatch time so callers always get the latest handler
      for (const eventName of Object.keys(eventsRef.current)) {
        es.addEventListener(eventName, (e) => {
          const handler = eventsRef.current[eventName];
          if (!handler) return;
          try {
            const data: unknown = JSON.parse((e as MessageEvent).data);
            handler(data);
          } catch {
            console.error('[useSSE] Failed to parse event:', eventName, (e as MessageEvent).data);
          }
        });
      }
    }

    connect();

    return () => {
      disposed = true;
      if (retryTimer !== null) clearTimeout(retryTimer);
      es?.close();
    };
  }, [url]);
}
