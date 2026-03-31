import { useLiveStore } from '../../stores/liveStore';
import { useSSE } from '../../hooks/useSSE';

function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}

export default function EventFeed() {
  const active = useLiveStore((s) => s.active);
  const events = useLiveStore((s) => s.events);
  const addEvent = useLiveStore((s) => s.addEvent);
  const setActive = useLiveStore((s) => s.setActive);

  // ── SSE connection (only when live is active) ─────────
  useSSE({
    url: active ? '/api/live/events' : null,
    events: {
      live_message: (data) =>
        addEvent({
          type: 'message',
          data: data as Record<string, unknown>,
          timestamp: Date.now(),
        }),
      live_error: (data) =>
        addEvent({
          type: 'error',
          data: data as Record<string, unknown>,
          timestamp: Date.now(),
        }),
      live_stopped: () => setActive(false),
    },
    onError: (retriesExhausted) =>
      addEvent({
        type: 'error',
        data: {
          detail: retriesExhausted
            ? 'Connection lost — please refresh the page'
            : 'Connection lost — retrying…',
        },
        timestamp: Date.now(),
      }),
  });

  // ── Empty state ───────────────────────────────────────
  if (events.length === 0) {
    return (
      <div className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <h2 className="card-title text-lg">Event Feed</h2>
          <div className="flex items-center justify-center py-8 text-base-content/50">
            {active
              ? 'Waiting for messages...'
              : 'No events yet. Start monitoring to see real-time messages.'}
          </div>
        </div>
      </div>
    );
  }

  // ── Event list ────────────────────────────────────────
  return (
    <div className="card bg-base-100 shadow-sm">
      <div className="card-body">
        <h2 className="card-title text-lg">Event Feed</h2>
        <div className="max-h-96 overflow-y-auto space-y-1">
          {events.map((event, index) => {
            const isError = event.type === 'error';
            const senderName =
              (event.data.sender_name as string | undefined) ?? '';
            const textPreview =
              (event.data.text as string | undefined) ?? '';
            const mediaType =
              (event.data.media_type as string | undefined) ?? '';
            const errorDetail =
              (event.data.detail as string | undefined) ??
              (event.data.error as string | undefined) ??
              'Unknown error';

            return (
              <div
                key={`${event.timestamp}-${index}`}
                className={`flex items-start gap-2 text-sm px-2 py-1.5 rounded ${
                  isError ? 'bg-error/10' : 'hover:bg-base-200'
                }`}
              >
                {/* Status dot */}
                <span
                  className={`mt-1.5 h-2 w-2 rounded-full shrink-0 ${
                    isError ? 'bg-error' : 'bg-success'
                  }`}
                />

                {/* Timestamp */}
                <span className="text-base-content/50 shrink-0 font-mono text-xs mt-0.5">
                  {formatTime(event.timestamp)}
                </span>

                {/* Content */}
                <div className="min-w-0 flex-1">
                  {isError ? (
                    <span className="text-error">{errorDetail}</span>
                  ) : (
                    <span>
                      {senderName && (
                        <span className="font-medium">{senderName}: </span>
                      )}
                      {textPreview
                        ? truncate(textPreview, 120)
                        : mediaType
                          ? `[${mediaType}]`
                          : '[message]'}
                      {textPreview && mediaType && (
                        <span className="text-base-content/50 ml-1">
                          [{mediaType}]
                        </span>
                      )}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
