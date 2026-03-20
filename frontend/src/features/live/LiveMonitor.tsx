import { useEffect, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { startLive, stopLive, getLiveStatus } from '../../api/live';
import { listChats } from '../../api/chats';
import { getTargetChats } from '../../api/transfer';
import { useLiveStore } from '../../stores/liveStore';
import { ApiError } from '../../api/client';
import type { LiveForwardStart } from '../../types/api';

type LiveMode = 'forward' | 'copy';
type LiveTargetType = 'saved_messages' | 'manual';

export default function LiveMonitor() {
  const active = useLiveStore((s) => s.active);
  const sourceChatId = useLiveStore((s) => s.sourceChatId);
  const mode = useLiveStore((s) => s.mode);
  const stats = useLiveStore((s) => s.stats);
  const setActive = useLiveStore((s) => s.setActive);
  const setStatus = useLiveStore((s) => s.setStatus);

  // ── Form state ──────────────────────────────────────
  const [selectedSourceChatId, setSelectedSourceChatId] = useState<
    number | undefined
  >(undefined);
  const [formMode, setFormMode] = useState<LiveMode>('forward');
  const [targetType, setTargetType] = useState<LiveTargetType>('saved_messages');
  const [targetChatId, setTargetChatId] = useState<number | undefined>(
    undefined,
  );
  const [includeText, setIncludeText] = useState(true);
  const [includeMedia, setIncludeMedia] = useState(true);
  const [keywordWhitelist, setKeywordWhitelist] = useState('');
  const [keywordBlacklist, setKeywordBlacklist] = useState('');
  const [submitError, setSubmitError] = useState<string | null>(null);

  // ── Hydrate from backend on mount ─────────────────────
  useEffect(() => {
    getLiveStatus()
      .then((s) => setStatus(s))
      .catch((err) => {
        console.error('Failed to fetch live status:', err);
        setSubmitError('Failed to load live forwarding status.');
      });
  }, [setStatus]);

  // ── Source chats query (Account A) ────────────────────
  const { data: sourceChatsData, isLoading: sourceChatsLoading } = useQuery({
    queryKey: ['liveSourceChats'],
    queryFn: () => listChats('account_a', { limit: 100 }),
    enabled: !active,
  });

  const sourceChats = sourceChatsData?.chats ?? [];

  // ── Target chats query (Account B) ────────────────────
  const { data: targetChatsData, isLoading: targetChatsLoading } = useQuery({
    queryKey: ['liveTargetChats'],
    queryFn: () => getTargetChats(),
    enabled: !active && targetType === 'manual',
  });

  const targetChats = targetChatsData?.chats ?? [];

  // ── Start mutation ────────────────────────────────────
  const startMutation = useMutation({
    mutationFn: startLive,
    onSuccess: (data) => {
      setStatus({
        active: true,
        source_chat_id: data.source_chat_id,
        mode: data.mode,
        stats: {},
      });
      setSubmitError(null);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitError(error.detail);
      } else {
        setSubmitError('An unexpected error occurred.');
      }
    },
  });

  // ── Stop mutation ─────────────────────────────────────
  const stopMutation = useMutation({
    mutationFn: stopLive,
    onSuccess: () => {
      setActive(false);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitError(error.detail);
      } else {
        setSubmitError('Failed to stop monitoring.');
      }
    },
  });

  // ── Handlers ──────────────────────────────────────────
  function handleStart() {
    setSubmitError(null);

    if (!selectedSourceChatId) {
      setSubmitError('Please select a source chat.');
      return;
    }

    if (targetType === 'manual' && !targetChatId) {
      setSubmitError('Please select a target chat.');
      return;
    }

    const config: LiveForwardStart = {
      source_chat_id: selectedSourceChatId,
      mode: formMode,
      target_type: targetType,
      ...(targetType === 'manual' && targetChatId
        ? { target_chat_id: targetChatId }
        : {}),
      include_text: includeText,
      include_media: includeMedia,
      keyword_whitelist: keywordWhitelist,
      keyword_blacklist: keywordBlacklist,
    };

    startMutation.mutate(config);
  }

  // ── Resolve source chat name ──────────────────────────
  const sourceChatName =
    sourceChats.find((c) => c.id === sourceChatId)?.title ??
    (sourceChatId ? `Chat ${sourceChatId}` : 'Unknown');

  // ── Active state ──────────────────────────────────────
  if (active) {
    return (
      <div className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <div className="flex items-center gap-3">
            <h2 className="card-title text-lg">Live Forwarding</h2>
            <span className="badge badge-success animate-pulse">LIVE</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm mt-2">
            <div>
              <span className="font-medium">Source:</span> {sourceChatName}
            </div>
            <div>
              <span className="font-medium">Mode:</span>{' '}
              {mode === 'forward' ? 'Forward mode' : 'Copy mode'}
            </div>
          </div>

          {/* Stats */}
          <div className="flex gap-4 mt-2">
            <div className="stat bg-base-200 rounded-box p-3">
              <div className="stat-title text-xs">Forwarded</div>
              <div className="stat-value text-lg">
                {(stats.forwarded ?? 0).toLocaleString()}
              </div>
            </div>
            <div className="stat bg-base-200 rounded-box p-3">
              <div className="stat-title text-xs">Errors</div>
              <div className="stat-value text-lg text-error">
                {(stats.failed ?? 0).toLocaleString()}
              </div>
            </div>
          </div>

          {submitError && (
            <div className="alert alert-error text-sm mt-2">{submitError}</div>
          )}

          <div className="card-actions justify-end mt-2">
            <button
              type="button"
              className="btn btn-error"
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
            >
              {stopMutation.isPending && (
                <span className="loading loading-spinner loading-sm" />
              )}
              Stop Monitoring
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── Start form (inactive state) ───────────────────────
  return (
    <div className="card bg-base-100 shadow-sm">
      <div className="card-body">
        <h2 className="card-title text-lg">Live Forwarding</h2>

        {/* ── Source chat ─────────────────────────────── */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">Source Chat</span>
          </label>
          {sourceChatsLoading ? (
            <div className="flex items-center gap-2 p-2 text-sm text-base-content/60">
              <span className="loading loading-spinner loading-xs" />
              Loading chats...
            </div>
          ) : (
            <select
              className="select select-bordered select-sm w-full"
              value={selectedSourceChatId ?? ''}
              onChange={(e) =>
                setSelectedSourceChatId(
                  e.target.value ? Number(e.target.value) : undefined,
                )
              }
            >
              <option value="">Select a chat...</option>
              {sourceChats.map((chat) => (
                <option key={chat.id} value={chat.id}>
                  {chat.title}
                </option>
              ))}
            </select>
          )}
        </div>

        {/* ── Mode ───────────────────────────────────── */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">Mode</span>
          </label>
          <div className="flex gap-4">
            <label className="label cursor-pointer gap-2">
              <input
                type="radio"
                name="liveMode"
                className="radio radio-primary radio-sm"
                checked={formMode === 'forward'}
                onChange={() => setFormMode('forward')}
              />
              <span className="label-text">Forward</span>
            </label>
            <label className="label cursor-pointer gap-2">
              <input
                type="radio"
                name="liveMode"
                className="radio radio-primary radio-sm"
                checked={formMode === 'copy'}
                onChange={() => setFormMode('copy')}
              />
              <span className="label-text">Copy</span>
            </label>
          </div>
        </div>

        {/* ── Target type ────────────────────────────── */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">Target</span>
          </label>
          <div className="flex gap-4">
            <label className="label cursor-pointer gap-2">
              <input
                type="radio"
                name="liveTargetType"
                className="radio radio-secondary radio-sm"
                checked={targetType === 'saved_messages'}
                onChange={() => {
                  setTargetType('saved_messages');
                  setTargetChatId(undefined);
                }}
              />
              <span className="label-text">Saved Messages</span>
            </label>
            <label className="label cursor-pointer gap-2">
              <input
                type="radio"
                name="liveTargetType"
                className="radio radio-secondary radio-sm"
                checked={targetType === 'manual'}
                onChange={() => setTargetType('manual')}
              />
              <span className="label-text">Specific Chat</span>
            </label>
          </div>
        </div>

        {/* ── Target chat dropdown ────────────────────── */}
        {targetType === 'manual' && (
          <div className="form-control">
            <label className="label">
              <span className="label-text">Target Chat</span>
            </label>
            {targetChatsLoading ? (
              <div className="flex items-center gap-2 p-2 text-sm text-base-content/60">
                <span className="loading loading-spinner loading-xs" />
                Loading chats...
              </div>
            ) : (
              <select
                className="select select-bordered select-sm w-full"
                value={targetChatId ?? ''}
                onChange={(e) =>
                  setTargetChatId(
                    e.target.value ? Number(e.target.value) : undefined,
                  )
                }
              >
                <option value="">Select a chat...</option>
                {targetChats.map((chat) => (
                  <option key={chat.id} value={chat.id}>
                    {chat.title}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* ── Content filters ────────────────────────── */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">Content Filters</span>
          </label>
          <div className="flex gap-4 flex-wrap">
            <label className="label cursor-pointer gap-2">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={includeText}
                onChange={(e) => setIncludeText(e.target.checked)}
              />
              <span className="label-text">Include text</span>
            </label>
            <label className="label cursor-pointer gap-2">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={includeMedia}
                onChange={(e) => setIncludeMedia(e.target.checked)}
              />
              <span className="label-text">Include media</span>
            </label>
          </div>
        </div>

        {/* ── Keywords ───────────────────────────────── */}
        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">
              Keyword Whitelist (optional)
            </span>
          </label>
          <input
            type="text"
            className="input input-bordered input-sm w-full"
            placeholder="comma-separated keywords"
            value={keywordWhitelist}
            onChange={(e) => setKeywordWhitelist(e.target.value)}
          />
        </div>

        <div className="form-control">
          <label className="label">
            <span className="label-text font-medium">
              Keyword Blacklist (optional)
            </span>
          </label>
          <input
            type="text"
            className="input input-bordered input-sm w-full"
            placeholder="comma-separated keywords"
            value={keywordBlacklist}
            onChange={(e) => setKeywordBlacklist(e.target.value)}
          />
        </div>

        {/* ── Error ──────────────────────────────────── */}
        {submitError && (
          <div className="alert alert-error text-sm mt-2">{submitError}</div>
        )}

        {/* ── Submit ─────────────────────────────────── */}
        <div className="card-actions justify-end mt-2">
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleStart}
            disabled={startMutation.isPending}
          >
            {startMutation.isPending && (
              <span className="loading loading-spinner loading-sm" />
            )}
            Start Monitoring
          </button>
        </div>
      </div>
    </div>
  );
}
