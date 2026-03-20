import { apiFetch } from './client';

export async function setupCredentials(apiId: number, apiHash: string) {
  return apiFetch<{ status: string }>('/api/setup/credentials', {
    method: 'POST',
    body: JSON.stringify({ api_id: apiId, api_hash: apiHash }),
  });
}
