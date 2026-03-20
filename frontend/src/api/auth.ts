import { apiFetch } from './client';
import type { AccountKey, AuthStatusResponse, AccountInfo } from '../types/api';

export async function getAuthStatus() {
  return apiFetch<AuthStatusResponse>('/api/auth/status');
}

export async function sendCode(account: AccountKey, phone: string) {
  return apiFetch<{ status: string }>(`/api/auth/send-code/${account}`, {
    method: 'POST',
    body: JSON.stringify({ phone }),
  });
}

export async function submitCode(account: AccountKey, code: string) {
  return apiFetch<{ status: string; user?: AccountInfo }>(
    `/api/auth/submit-code/${account}`,
    { method: 'POST', body: JSON.stringify({ code }) },
  );
}

export async function submit2FA(account: AccountKey, password: string) {
  return apiFetch<{ status: string; user?: AccountInfo }>(
    `/api/auth/submit-2fa/${account}`,
    { method: 'POST', body: JSON.stringify({ password }) },
  );
}

export async function logout(account: AccountKey) {
  return apiFetch<{ status: string }>(`/api/auth/logout/${account}`, {
    method: 'POST',
  });
}
