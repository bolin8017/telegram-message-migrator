import { apiFetch } from './client';

export async function deleteUserData() {
  return apiFetch<{ status: string }>('/api/user/data', { method: 'DELETE' });
}
