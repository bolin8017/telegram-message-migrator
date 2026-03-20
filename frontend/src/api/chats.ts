import { apiFetch } from './client';
import type {
  AccountKey,
  ChatListResponse,
  DateRangeResponse,
  MessageDatesResponse,
  MessageListResponse,
} from '../types/api';

export async function listChats(
  account: AccountKey,
  params: { limit?: number; offset?: number; search?: string; sort?: string } = {},
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset) qs.set('offset', String(params.offset));
  if (params.search) qs.set('search', params.search);
  if (params.sort) qs.set('sort', params.sort);
  return apiFetch<ChatListResponse>(`/api/chats/${account}?${qs}`);
}

export async function listMessages(
  account: AccountKey,
  chatId: number,
  params: { limit?: number; offset_id?: number; date_from?: string; date_to?: string } = {},
) {
  const qs = new URLSearchParams();
  if (params.limit) qs.set('limit', String(params.limit));
  if (params.offset_id) qs.set('offset_id', String(params.offset_id));
  if (params.date_from) qs.set('date_from', params.date_from);
  if (params.date_to) qs.set('date_to', params.date_to);
  return apiFetch<MessageListResponse>(`/api/chats/${account}/${chatId}/messages?${qs}`);
}

export async function getChatInfo(account: AccountKey, chatId: number) {
  return apiFetch<{ id: number; title: string; type: string }>(
    `/api/chats/${account}/${chatId}/info`,
  );
}

export async function getDateRange(account: AccountKey, chatId: number) {
  return apiFetch<DateRangeResponse>(`/api/chats/${account}/${chatId}/date-range`);
}

export async function getMessageDates(
  account: AccountKey,
  chatId: number,
  year: number,
  month: number,
) {
  const qs = new URLSearchParams({ year: String(year), month: String(month) });
  return apiFetch<MessageDatesResponse>(`/api/chats/${account}/${chatId}/message-dates?${qs}`);
}
