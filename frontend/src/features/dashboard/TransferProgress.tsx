import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  pauseJob,
  resumeJob,
  cancelJob,
  getTransferStatus,
} from '../../api/transfer';
import { useTransferStore, type BackendProgress } from '../../stores/transferStore';
import { useSSE } from '../../hooks/useSSE';
import FloodWaitTimer from '../../components/FloodWaitTimer';
import type { TransferStatus as TransferStatusType } from '../../types/api';

function formatTime(totalSeconds: number): string {
  const mins = Math.floor(totalSeconds / 60);
  const secs = Math.floor(totalSeconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export default function TransferProgress() {
  const jobId = useTransferStore((s) => s.jobId);
  const status = useTransferStore((s) => s.status);
  const totalMessages = useTransferStore((s) => s.totalMessages);
  const transferredCount = useTransferStore((s) => s.transferredCount);
  const failedCount = useTransferStore((s) => s.failedCount);
  const skippedCount = useTransferStore((s) => s.skippedCount);
  const percent = useTransferStore((s) => s.percent);
  const elapsedSeconds = useTransferStore((s) => s.elapsedSeconds);
  const estimatedRemainingSeconds = useTransferStore(
    (s) => s.estimatedRemainingSeconds,
  );
  const lastError = useTransferStore((s) => s.lastError);
  const isRateLimited = useTransferStore((s) => s.isRateLimited);
  const rateLimitWaitSeconds = useTransferStore(
    (s) => s.rateLimitWaitSeconds,
  );
  const updateProgress = useTransferStore((s) => s.updateProgress);
  const setStatus = useTransferStore((s) => s.setStatus);
  const reset = useTransferStore((s) => s.reset);

  // ── Refs for optimized DOM writes ────────────────────
  const percentRef = useRef<HTMLProgressElement>(null);
  const countRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (percentRef.current) percentRef.current.value = percent;
    if (countRef.current)
      countRef.current.textContent = String(transferredCount);
  }, [percent, transferredCount]);

  // ── Cancel confirmation ──────────────────────────────
  const [showCancelModal, setShowCancelModal] = useState(false);
  const cancelModalRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (showCancelModal) {
      cancelModalRef.current?.showModal();
    } else {
      cancelModalRef.current?.close();
    }
  }, [showCancelModal]);

  // ── SSE connection ───────────────────────────────────
  const sseUrl = jobId ? `/api/transfer/progress/${jobId}` : null;

  const handleProgress = useCallback(
    (data: unknown) => {
      updateProgress(data as BackendProgress);
    },
    [updateProgress],
  );

  const handleCompleted = useCallback(() => {
    setStatus('completed');
  }, [setStatus]);

  const handleFailed = useCallback(() => {
    setStatus('failed');
  }, [setStatus]);

  const handleCancelled = useCallback(() => {
    setStatus('cancelled');
  }, [setStatus]);

  const handleAuthExpired = useCallback(() => {
    setStatus('failed');
    updateProgress({ last_error: 'Telegram session expired. Please re-login.' });
  }, [setStatus, updateProgress]);

  const handleAutoPaused = useCallback(() => {
    setStatus('paused');
    updateProgress({ last_error: 'Auto-paused due to repeated rate limiting.' });
  }, [setStatus, updateProgress]);

  const handleDailyCap = useCallback(() => {
    setStatus('paused');
    updateProgress({ last_error: 'Daily message cap reached.' });
  }, [setStatus, updateProgress]);

  const handleOpen = useCallback(() => {
    getTransferStatus()
      .then((s) => {
        if (s.progress)
          updateProgress(s.progress as unknown as BackendProgress);
        if (s.status) setStatus(s.status as TransferStatusType);
      })
      .catch((err) => {
        console.error('Failed to fetch initial transfer status:', err);
        updateProgress({ last_error: 'Failed to load transfer status.' });
      });
  }, [updateProgress, setStatus]);

  const handleSSEError = useCallback(() => {
    updateProgress({ last_error: 'Connection lost. Attempting to reconnect...' });
  }, [updateProgress]);

  useSSE({
    url: sseUrl,
    events: {
      progress: handleProgress,
      job_completed: handleCompleted,
      job_failed: handleFailed,
      job_cancelled: handleCancelled,
      auth_expired: handleAuthExpired,
      auto_paused: handleAutoPaused,
      daily_cap: handleDailyCap,
    },
    onOpen: handleOpen,
    onError: handleSSEError,
  });

  // ── Pause / Resume / Cancel mutations ────────────────
  const pauseMutation = useMutation({
    mutationFn: pauseJob,
    onSuccess: () => setStatus('paused'),
  });

  const resumeMutation = useMutation({
    mutationFn: resumeJob,
    onSuccess: () => setStatus('running'),
  });

  const cancelMutation = useMutation({
    mutationFn: cancelJob,
    onSuccess: () => {
      setStatus('cancelled');
      setShowCancelModal(false);
    },
  });

  // ── Derived state ────────────────────────────────────
  const isTerminal =
    status === 'completed' || status === 'failed' || status === 'cancelled';
  const isRunning = status === 'running';
  const isPaused = status === 'paused';

  const handleFloodWaitExpire = useCallback(() => {
    updateProgress({ is_rate_limited: false, rate_limit_wait_seconds: null });
  }, [updateProgress]);

  return (
    <div className="card bg-base-100 shadow-sm">
      <div className="card-body">
        <h2 className="card-title text-lg">Transfer Progress</h2>

        {/* ── Terminal states ────────────────────────── */}
        {status === 'completed' && (
          <div className="alert alert-success">
            <div>
              <p className="font-medium">Transfer completed!</p>
              <p className="text-sm">
                {transferredCount.toLocaleString()} transferred, {failedCount}{' '}
                failed, {skippedCount} skipped in {formatTime(elapsedSeconds)}
              </p>
            </div>
          </div>
        )}

        {status === 'failed' && (
          <div className="alert alert-error">
            <div>
              <p className="font-medium">Transfer failed</p>
              {lastError && <p className="text-sm">{lastError}</p>}
              {lastError?.includes('session expired') && (
                <p className="text-sm font-medium">
                  Please re-login from the account settings to continue.
                </p>
              )}
              <p className="text-sm">
                {transferredCount.toLocaleString()} transferred before failure
              </p>
            </div>
          </div>
        )}

        {status === 'cancelled' && (
          <div className="alert alert-warning">
            <div>
              <p className="font-medium">Transfer cancelled</p>
              <p className="text-sm">
                {transferredCount.toLocaleString()} transferred before
                cancellation
              </p>
            </div>
          </div>
        )}

        {isTerminal && (
          <div className="card-actions justify-end mt-2">
            <button type="button" className="btn btn-primary" onClick={reset}>
              New Transfer
            </button>
          </div>
        )}

        {/* ── Active progress ───────────────────────── */}
        {!isTerminal && (
          <>
            {/* Progress bar */}
            <progress
              ref={percentRef}
              className="progress progress-primary w-full"
              value={percent}
              max={100}
            />

            {/* Stats row */}
            <div className="text-sm text-base-content/80">
              <span ref={countRef}>{transferredCount}</span> /{' '}
              {totalMessages.toLocaleString()} transferred, {failedCount}{' '}
              failed, {skippedCount} skipped
            </div>

            {/* Time info */}
            <div className="text-sm text-base-content/60 flex gap-4">
              <span>Elapsed: {formatTime(elapsedSeconds)}</span>
              <span>
                ETA:{' '}
                {estimatedRemainingSeconds != null
                  ? formatTime(estimatedRemainingSeconds)
                  : 'calculating...'}
              </span>
            </div>

            {/* FloodWait indicator */}
            {isRateLimited && rateLimitWaitSeconds != null && (
              <FloodWaitTimer
                seconds={rateLimitWaitSeconds}
                onExpire={handleFloodWaitExpire}
              />
            )}

            {/* Last error (non-terminal) */}
            {lastError && (
              <div className="alert alert-error text-sm">{lastError}</div>
            )}

            {/* Controls */}
            <div className="card-actions justify-end mt-2 gap-2">
              {isRunning && (
                <button
                  type="button"
                  className="btn btn-warning btn-sm"
                  onClick={() => pauseMutation.mutate()}
                  disabled={pauseMutation.isPending}
                >
                  {pauseMutation.isPending && (
                    <span className="loading loading-spinner loading-xs" />
                  )}
                  Pause
                </button>
              )}

              {isPaused && (
                <button
                  type="button"
                  className="btn btn-success btn-sm"
                  onClick={() => resumeMutation.mutate()}
                  disabled={resumeMutation.isPending}
                >
                  {resumeMutation.isPending && (
                    <span className="loading loading-spinner loading-xs" />
                  )}
                  Resume
                </button>
              )}

              <button
                type="button"
                className="btn btn-error btn-sm"
                onClick={() => setShowCancelModal(true)}
                disabled={cancelMutation.isPending}
              >
                Cancel Transfer
              </button>
            </div>
          </>
        )}
      </div>

      {/* ── Cancel confirmation modal ────────────────── */}
      <dialog
        ref={cancelModalRef}
        className="modal"
        onClose={() => setShowCancelModal(false)}
      >
        <div className="modal-box">
          <h3 className="font-bold text-lg">Cancel Transfer?</h3>
          <p className="py-4">
            Are you sure you want to cancel the current transfer? This action
            cannot be undone. {transferredCount.toLocaleString()} messages have
            been transferred so far.
          </p>
          <div className="modal-action">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => setShowCancelModal(false)}
              disabled={cancelMutation.isPending}
            >
              Keep Running
            </button>
            <button
              type="button"
              className="btn btn-error"
              onClick={() => cancelMutation.mutate()}
              disabled={cancelMutation.isPending}
            >
              {cancelMutation.isPending && (
                <span className="loading loading-spinner loading-sm" />
              )}
              Cancel Transfer
            </button>
          </div>
        </div>
        <form method="dialog" className="modal-backdrop">
          <button type="submit">close</button>
        </form>
      </dialog>
    </div>
  );
}
