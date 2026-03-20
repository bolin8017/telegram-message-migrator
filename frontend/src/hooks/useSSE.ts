import { useEffect, useRef } from 'react';

interface UseSSEOptions {
  url: string | null;
  events: Record<string, (data: unknown) => void>;
  onError?: () => void;
  onOpen?: () => void;
}

export function useSSE({ url, events, onError, onOpen }: UseSSEOptions) {
  const eventsRef = useRef(events);
  eventsRef.current = events;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;

  useEffect(() => {
    if (!url) return;
    const es = new EventSource(url, { withCredentials: true });
    es.onopen = () => onOpenRef.current?.();
    es.onerror = () => onErrorRef.current?.();

    // Read from ref at dispatch time so callers always get the latest handler
    for (const eventName of Object.keys(eventsRef.current)) {
      es.addEventListener(eventName, (e) => {
        const handler = eventsRef.current[eventName];
        if (!handler) return;
        try {
          const data: unknown = JSON.parse((e as MessageEvent).data);
          handler(data);
        } catch {
          handler((e as MessageEvent).data);
        }
      });
    }

    return () => es.close();
  }, [url]);
}
