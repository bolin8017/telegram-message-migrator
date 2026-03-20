import { apiFetch } from './client';
import type { LiveForwardStart, LiveStatusResponse } from '../types/api';

export async function startLive(config: LiveForwardStart) {
  return apiFetch<{ status: string; source_chat_id: number; mode: string }>(
    '/api/live/start',
    { method: 'POST', body: JSON.stringify(config) },
  );
}

export async function stopLive() {
  return apiFetch<{ status: string; stats: Record<string, number> }>(
    '/api/live/stop',
    { method: 'POST' },
  );
}

export async function getLiveStatus() {
  return apiFetch<LiveStatusResponse>('/api/live/status');
}
