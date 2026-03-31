// TypeScript types matching backend Pydantic models (app/models.py)
// All date fields are ISO 8601 strings (serialized by FastAPI).

// ── Auth ──────────────────────────────────────────────

export type AccountKey = 'account_a' | 'account_b';

export interface AccountInfo {
  phone: string;
  name: string;
  username: string | null;
  is_authorized: boolean;
  session_expired: boolean;
}

export interface AuthStatusResponse {
  account_a: AccountInfo | null;
  account_b: AccountInfo | null;
  has_credentials: boolean;
}

// ── Chats ─────────────────────────────────────────────

export interface ChatInfo {
  id: number;
  title: string;
  type: 'user' | 'group' | 'supergroup' | 'channel';
  unread_count: number;
  last_message_date: string | null;
}

export interface MessageInfo {
  id: number;
  date: string;
  sender_name: string;
  text: string | null;
  media_type: string | null;
  media_filename: string | null;
  media_size: number | null;
  has_media: boolean;
  reply_to_msg_id: number | null;
}

export interface ChatListResponse {
  chats: ChatInfo[];
  has_more: boolean;
}

export interface MessageListResponse {
  messages: MessageInfo[];
  has_more: boolean;
  total_count: number | null;
}

export interface DateRangeResponse {
  earliest: string | null;
  latest: string | null;
  total: number;
}

export interface MessageDatesResponse {
  dates: string[];
}

// ── Transfer ──────────────────────────────────────────

export type TransferMode = 'forward' | 'copy';

export type TargetType = 'saved_messages' | 'manual';

export type TransferStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface TransferJobCreate {
  source_account: AccountKey;
  source_chat_id: number;
  mode: TransferMode;
  target_type: TargetType;
  target_chat_id?: number;
  date_from?: string;
  date_to?: string;
  include_text: boolean;
  include_media: boolean;
  max_file_size_mb?: number;
  keyword_whitelist: string;
  keyword_blacklist: string;
}

export interface TransferProgress {
  total_messages: number;
  transferred_count: number;
  failed_count: number;
  skipped_count: number;
  current_message_id: number | null;
  percent: number;
  elapsed_seconds: number;
  estimated_remaining_seconds: number | null;
  last_error: string | null;
  is_rate_limited: boolean;
  rate_limit_wait_seconds: number | null;
}

/** Not a Pydantic model — derived from route return shape (app/routes/transfer.py). */
export interface TransferStatusResponse {
  job_id: string | null;
  status: TransferStatus | 'idle';
  progress: TransferProgress | null;
}

// ── Live Forwarding ───────────────────────────────────

export interface LiveForwardStart {
  source_chat_id: number;
  mode: string;
  target_type: string;
  target_chat_id?: number;
  include_text: boolean;
  include_media: boolean;
  keyword_whitelist: string;
  keyword_blacklist: string;
}

/** Not a Pydantic model — derived from route return shape (app/routes/live.py). */
export interface LiveStatusResponse {
  active: boolean;
  source_chat_id: number | null;
  mode: string | null;
  stats: Record<string, number>;
}

// ── Error ─────────────────────────────────────────────

export interface ApiErrorResponse {
  detail: string;
  wait_seconds?: number;
}
