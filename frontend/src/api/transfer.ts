import { apiFetch } from './client';
import type {
  AccountKey,
  ChatInfo,
  TransferJobCreate,
  TransferStatusResponse,
} from '../types/api';

export async function createJob(config: TransferJobCreate) {
  return apiFetch<{ job_id: string }>('/api/transfer/jobs', {
    method: 'POST',
    body: JSON.stringify(config),
  });
}

export async function pauseJob() {
  return apiFetch<{ status: string }>('/api/transfer/jobs/pause', { method: 'POST' });
}

export async function resumeJob() {
  return apiFetch<{ status: string }>('/api/transfer/jobs/resume', { method: 'POST' });
}

export async function cancelJob() {
  return apiFetch<{ status: string }>('/api/transfer/jobs/cancel', { method: 'POST' });
}

export async function getTransferStatus() {
  return apiFetch<TransferStatusResponse>('/api/transfer/status');
}

export async function estimateCount(
  sourceChatId: number,
  sourceAccount: AccountKey = 'account_a',
  dateFrom?: string,
  dateTo?: string,
) {
  const qs = new URLSearchParams({
    source_chat_id: String(sourceChatId),
    source_account: sourceAccount,
  });
  if (dateFrom) qs.set('date_from', dateFrom);
  if (dateTo) qs.set('date_to', dateTo);
  return apiFetch<{ count: number; total: number; capped: boolean }>(
    `/api/transfer/estimate-count?${qs}`,
  );
}

export async function getTargetChats(targetAccount: AccountKey = 'account_b') {
  const qs = new URLSearchParams({ target_account: targetAccount });
  return apiFetch<{ chats: ChatInfo[] }>(`/api/transfer/target-chats?${qs}`);
}
