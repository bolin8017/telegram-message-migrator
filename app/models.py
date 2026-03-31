from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

# ── Auth ──────────────────────────────────────────────


class AccountInfo(BaseModel):
    phone: str
    name: str
    username: str | None = None
    is_authorized: bool = True
    session_expired: bool = False  # distinguish "never logged in" vs "session expired"


class AuthStatusResponse(BaseModel):
    account_a: AccountInfo | None = None
    account_b: AccountInfo | None = None
    has_credentials: bool = False


class SendCodeRequest(BaseModel):
    phone: str


class SubmitCodeRequest(BaseModel):
    code: str
    # phone_code_hash removed — stored server-side via pending_token cookie


class Submit2FARequest(BaseModel):
    password: str


# ── Setup (multi-user) ───────────────────────────────


class SetupCredentialsRequest(BaseModel):
    api_id: int
    api_hash: str


# ── Chats ─────────────────────────────────────────────


class ChatInfo(BaseModel):
    id: int
    title: str
    type: Literal["user", "group", "supergroup", "channel"]
    unread_count: int = 0
    last_message_date: datetime | None = None


class MessageInfo(BaseModel):
    id: int
    date: datetime
    sender_name: str = ""
    text: str | None = None
    media_type: str | None = None
    media_filename: str | None = None
    media_size: int | None = None
    has_media: bool = False
    reply_to_msg_id: int | None = None


class ChatListResponse(BaseModel):
    chats: list[ChatInfo]
    has_more: bool = False


class MessageListResponse(BaseModel):
    messages: list[MessageInfo]
    has_more: bool = False
    total_count: int | None = None


# ── Live Forwarding ───────────────────────────────────


class TransferMode(StrEnum):
    forward = "forward"
    copy = "copy"


class TargetType(StrEnum):
    saved_messages = "saved_messages"
    manual = "manual"


class LiveForwardStart(BaseModel):
    source_chat_id: int
    mode: TransferMode = TransferMode.forward
    target_type: TargetType = TargetType.saved_messages
    target_chat_id: int | None = None
    include_text: bool = True
    include_media: bool = True
    keyword_whitelist: str = ""
    keyword_blacklist: str = ""


class TransferJobCreate(BaseModel):
    source_account: Literal["account_a", "account_b"] = "account_a"
    source_chat_id: int
    mode: TransferMode = TransferMode.forward
    target_type: TargetType = TargetType.saved_messages
    target_chat_id: int | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    # Message filters
    include_text: bool = True
    include_media: bool = True
    max_file_size_mb: int | None = None  # skip files larger than this
    # Keyword filters (comma-separated strings from form input)
    keyword_whitelist: str = ""  # only transfer if text contains ANY of these
    keyword_blacklist: str = ""  # skip if text contains ANY of these


class TransferStatus(StrEnum):
    pending = "pending"
    running = "running"
    paused = "paused"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TransferProgress(BaseModel):
    total_messages: int = 0
    transferred_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    current_message_id: int | None = None
    percent: float = 0.0
    elapsed_seconds: float = 0.0
    estimated_remaining_seconds: float | None = None
    last_error: str | None = None
    is_rate_limited: bool = False
    rate_limit_wait_seconds: int | None = None
    mode: str | None = None


class TransferJob(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    config: TransferJobCreate
    status: TransferStatus = TransferStatus.pending
    progress: TransferProgress = TransferProgress()
