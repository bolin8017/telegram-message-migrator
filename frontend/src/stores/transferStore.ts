import { create } from 'zustand';
import type { TransferStatus, TransferJobCreate } from '../types/api';

export interface BackendProgress {
  total_messages?: number;
  transferred_count?: number;
  failed_count?: number;
  skipped_count?: number;
  percent?: number;
  elapsed_seconds?: number;
  estimated_remaining_seconds?: number | null;
  last_error?: string | null;
  is_rate_limited?: boolean;
  rate_limit_wait_seconds?: number | null;
}

interface TransferState {
  jobId: string | null;
  status: TransferStatus | 'idle';
  config: Partial<TransferJobCreate>;
  // Progress (flat for selector granularity)
  totalMessages: number;
  transferredCount: number;
  failedCount: number;
  skippedCount: number;
  percent: number;
  elapsedSeconds: number;
  estimatedRemainingSeconds: number | null;
  lastError: string | null;
  isRateLimited: boolean;
  rateLimitWaitSeconds: number | null;
  // Actions
  setJobId: (id: string | null) => void;
  setStatus: (status: TransferStatus | 'idle') => void;
  setConfig: (config: Partial<TransferJobCreate>) => void;
  updateProgress: (progress: BackendProgress) => void;
  reset: () => void;
}

const initialState = {
  jobId: null as string | null,
  status: 'idle' as TransferStatus | 'idle',
  config: {} as Partial<TransferJobCreate>,
  totalMessages: 0,
  transferredCount: 0,
  failedCount: 0,
  skippedCount: 0,
  percent: 0,
  elapsedSeconds: 0,
  estimatedRemainingSeconds: null as number | null,
  lastError: null as string | null,
  isRateLimited: false,
  rateLimitWaitSeconds: null as number | null,
};

export const useTransferStore = create<TransferState>()((set) => ({
  ...initialState,
  setJobId: (id) => set({ jobId: id }),
  setStatus: (status) => set({ status }),
  setConfig: (config) => set({ config }),
  updateProgress: (p) =>
    set((state) => ({
      totalMessages: p.total_messages !== undefined ? p.total_messages : state.totalMessages,
      transferredCount: p.transferred_count !== undefined ? p.transferred_count : state.transferredCount,
      failedCount: p.failed_count !== undefined ? p.failed_count : state.failedCount,
      skippedCount: p.skipped_count !== undefined ? p.skipped_count : state.skippedCount,
      percent: p.percent !== undefined ? p.percent : state.percent,
      elapsedSeconds: p.elapsed_seconds !== undefined ? p.elapsed_seconds : state.elapsedSeconds,
      estimatedRemainingSeconds: p.estimated_remaining_seconds !== undefined ? p.estimated_remaining_seconds : state.estimatedRemainingSeconds,
      lastError: p.last_error !== undefined ? p.last_error : state.lastError,
      isRateLimited: p.is_rate_limited !== undefined ? p.is_rate_limited : state.isRateLimited,
      rateLimitWaitSeconds: p.rate_limit_wait_seconds !== undefined ? p.rate_limit_wait_seconds : state.rateLimitWaitSeconds,
    })),
  reset: () => set(initialState),
}));
