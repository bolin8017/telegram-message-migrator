import { describe, it, expect, beforeEach } from 'vitest';
import { useTransferStore } from '../../src/stores/transferStore';

beforeEach(() => {
  useTransferStore.setState(useTransferStore.getInitialState());
});

describe('transferStore', () => {
  it('starts idle with zero progress', () => {
    const s = useTransferStore.getState();
    expect(s.status).toBe('idle');
    expect(s.jobId).toBeNull();
    expect(s.percent).toBe(0);
    expect(s.totalMessages).toBe(0);
    expect(s.transferredCount).toBe(0);
    expect(s.failedCount).toBe(0);
    expect(s.skippedCount).toBe(0);
    expect(s.elapsedSeconds).toBe(0);
    expect(s.estimatedRemainingSeconds).toBeNull();
    expect(s.lastError).toBeNull();
    expect(s.isRateLimited).toBe(false);
    expect(s.rateLimitWaitSeconds).toBeNull();
  });

  it('sets jobId', () => {
    useTransferStore.getState().setJobId('job-abc');
    expect(useTransferStore.getState().jobId).toBe('job-abc');
  });

  it('sets status', () => {
    useTransferStore.getState().setStatus('running');
    expect(useTransferStore.getState().status).toBe('running');
  });

  it('sets config', () => {
    useTransferStore.getState().setConfig({ source_chat_id: 42, mode: 'copy' });
    expect(useTransferStore.getState().config).toEqual({
      source_chat_id: 42,
      mode: 'copy',
    });
  });

  it('updateProgress maps snake_case to camelCase', () => {
    useTransferStore.getState().updateProgress({
      total_messages: 100,
      transferred_count: 42,
      failed_count: 3,
      skipped_count: 5,
      percent: 42.0,
      elapsed_seconds: 120,
      estimated_remaining_seconds: 180,
      last_error: null,
      is_rate_limited: false,
      rate_limit_wait_seconds: null,
    });
    const s = useTransferStore.getState();
    expect(s.totalMessages).toBe(100);
    expect(s.transferredCount).toBe(42);
    expect(s.failedCount).toBe(3);
    expect(s.skippedCount).toBe(5);
    expect(s.percent).toBe(42.0);
    expect(s.elapsedSeconds).toBe(120);
    expect(s.estimatedRemainingSeconds).toBe(180);
    expect(s.lastError).toBeNull();
    expect(s.isRateLimited).toBe(false);
    expect(s.rateLimitWaitSeconds).toBeNull();
  });

  it('updateProgress handles rate-limited state', () => {
    useTransferStore.getState().updateProgress({
      total_messages: 100,
      transferred_count: 50,
      failed_count: 0,
      skipped_count: 0,
      percent: 50.0,
      elapsed_seconds: 300,
      estimated_remaining_seconds: 300,
      last_error: 'FloodWait',
      is_rate_limited: true,
      rate_limit_wait_seconds: 60,
    });
    const s = useTransferStore.getState();
    expect(s.isRateLimited).toBe(true);
    expect(s.rateLimitWaitSeconds).toBe(60);
    expect(s.lastError).toBe('FloodWait');
  });

  it('updateProgress handles partial data with defaults', () => {
    useTransferStore.getState().updateProgress({
      total_messages: 50,
      transferred_count: 10,
    });
    const s = useTransferStore.getState();
    expect(s.totalMessages).toBe(50);
    expect(s.transferredCount).toBe(10);
    expect(s.failedCount).toBe(0);
    expect(s.percent).toBe(0);
    expect(s.isRateLimited).toBe(false);
  });

  it('updateProgress with partial data preserves existing values', () => {
    // First, set full progress
    useTransferStore.getState().updateProgress({
      total_messages: 100,
      transferred_count: 50,
      failed_count: 2,
      skipped_count: 3,
      percent: 50.0,
      elapsed_seconds: 200,
      estimated_remaining_seconds: 200,
      last_error: null,
      is_rate_limited: false,
      rate_limit_wait_seconds: null,
    });
    // Then, update only last_error
    useTransferStore.getState().updateProgress({
      last_error: 'some error',
    });
    const s = useTransferStore.getState();
    // Previously set fields must be preserved
    expect(s.transferredCount).toBe(50);
    expect(s.totalMessages).toBe(100);
    expect(s.failedCount).toBe(2);
    expect(s.skippedCount).toBe(3);
    expect(s.percent).toBe(50.0);
    expect(s.elapsedSeconds).toBe(200);
    expect(s.estimatedRemainingSeconds).toBe(200);
    expect(s.isRateLimited).toBe(false);
    expect(s.rateLimitWaitSeconds).toBeNull();
    // Only last_error should have changed
    expect(s.lastError).toBe('some error');
  });

  it('reset clears everything', () => {
    useTransferStore.getState().setJobId('job123');
    useTransferStore.getState().setStatus('running');
    useTransferStore.getState().updateProgress({
      total_messages: 100,
      transferred_count: 42,
      failed_count: 3,
      skipped_count: 5,
      percent: 42.0,
      elapsed_seconds: 120,
      estimated_remaining_seconds: 180,
      last_error: null,
      is_rate_limited: false,
      rate_limit_wait_seconds: null,
    });
    useTransferStore.getState().reset();
    const s = useTransferStore.getState();
    expect(s.jobId).toBeNull();
    expect(s.status).toBe('idle');
    expect(s.percent).toBe(0);
    expect(s.totalMessages).toBe(0);
    expect(s.transferredCount).toBe(0);
  });
});
