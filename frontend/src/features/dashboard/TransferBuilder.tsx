import { useCallback, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import AccountCard from './AccountCard';
import ChatSelectModal from './ChatSelectModal';
import MessageCalendar from './MessageCalendar';
import TransferConfirmDialog from './TransferConfirmDialog';
import { createJob, estimateCount, getTargetChats } from '../../api/transfer';
import { listMessages } from '../../api/chats';
import { useTransferStore } from '../../stores/transferStore';
import { ApiError } from '../../api/client';
import type {
  AccountKey,
  ChatInfo,
  TransferMode,
  TargetType,
  TransferJobCreate,
} from '../../types/api';

export default function TransferBuilder() {
  // ── Account & chat selection ─────────────────────
  const [sourceAccount, setSourceAccount] = useState<AccountKey>('account_a');
  const [selectedChat, setSelectedChat] = useState<ChatInfo | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const targetAccount: AccountKey = sourceAccount === 'account_a' ? 'account_b' : 'account_a';

  // ── Transfer settings ────────────────────────────
  const [mode, setMode] = useState<TransferMode>('forward');
  const [targetType, setTargetType] = useState<TargetType>('saved_messages');
  const [targetChatId, setTargetChatId] = useState<number | undefined>();
  const [includeText, setIncludeText] = useState(true);
  const [includeMedia, setIncludeMedia] = useState(true);
  const [maxFileSizeMb, setMaxFileSizeMb] = useState('');
  const [keywordWhitelist, setKeywordWhitelist] = useState('');
  const [keywordBlacklist, setKeywordBlacklist] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);

  // ── Calendar state ───────────────────────────────
  const [calendarMonth, setCalendarMonth] = useState(new Date());
  const [dateRange, setDateRange] = useState<{ from: Date | undefined; to: Date | undefined }>({
    from: undefined,
    to: undefined,
  });

  // ── Preview state ────────────────────────────────
  const [previewOpen, setPreviewOpen] = useState(false);

  // ── Confirm dialog ───────────────────────────────
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const setJobId = useTransferStore((s) => s.setJobId);
  const setStatus = useTransferStore((s) => s.setStatus);

  // ── Account change handler ───────────────────────
  const handleSourceAccountChange = useCallback((account: AccountKey) => {
    setSourceAccount(account);
    setSelectedChat(null);
    setDateRange({ from: undefined, to: undefined });
    setTargetChatId(undefined);
    setPreviewOpen(false);
  }, []);

  // ── Chat selection handler ───────────────────────
  const handleChatSelect = useCallback((chat: ChatInfo) => {
    setSelectedChat(chat);
    setDateRange({ from: undefined, to: undefined });
    setPreviewOpen(true);
    // Reset calendar to current month (dateRange query will update fromMonth/toMonth)
    setCalendarMonth(new Date());
  }, []);

  // ── Target chats query ───────────────────────────
  const { data: targetChatsData, isLoading: targetChatsLoading } = useQuery({
    queryKey: ['targetChats', targetAccount],
    queryFn: () => getTargetChats(targetAccount),
    enabled: targetType === 'manual',
    staleTime: 2 * 60 * 1000,
  });
  const targetChats = targetChatsData?.chats ?? [];

  // ── Estimate query ───────────────────────────────
  // Format as ISO date string with UTC midnight for backend datetime parsing
  const dateFromStr = dateRange.from
    ? `${dateRange.from.getFullYear()}-${String(dateRange.from.getMonth() + 1).padStart(2, '0')}-${String(dateRange.from.getDate()).padStart(2, '0')}T00:00:00Z`
    : undefined;
  const dateToStr = dateRange.to
    ? `${dateRange.to.getFullYear()}-${String(dateRange.to.getMonth() + 1).padStart(2, '0')}-${String(dateRange.to.getDate()).padStart(2, '0')}T23:59:59Z`
    : undefined;

  const { data: estimateData, isFetching: estimateFetching } = useQuery({
    queryKey: ['transferEstimate', selectedChat?.id, sourceAccount, dateFromStr, dateToStr],
    queryFn: () => estimateCount(selectedChat!.id, sourceAccount, dateFromStr, dateToStr),
    enabled: !!selectedChat,
  });

  // ── Preview messages query ───────────────────────
  const { data: previewData, isLoading: previewLoading } = useQuery({
    queryKey: ['previewMessages', sourceAccount, selectedChat?.id],
    queryFn: () => listMessages(sourceAccount, selectedChat!.id, { limit: 5 }),
    enabled: !!selectedChat && previewOpen,
    staleTime: 2 * 60 * 1000,
  });
  const previewMessages = previewData?.messages ?? [];

  // ── Create job mutation ──────────────────────────
  const createMutation = useMutation({
    mutationFn: createJob,
    onSuccess: (data) => {
      setJobId(data.job_id);
      setStatus('running');
      setConfirmOpen(false);
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        setSubmitError(error.status === 409 ? 'A transfer job is already running.' : error.detail);
      } else {
        setSubmitError('An unexpected error occurred.');
      }
    },
  });

  // ── Validation ───────────────────────────────────
  const handleSubmit = useCallback(() => {
    setValidationError(null);
    setSubmitError(null);

    if (!selectedChat) {
      setValidationError('Please select a source chat.');
      return;
    }
    if (targetType === 'manual' && !targetChatId) {
      setValidationError('Please select a target chat.');
      return;
    }

    setConfirmOpen(true);
  }, [selectedChat, targetType, targetChatId]);

  const handleConfirm = useCallback(() => {
    if (!selectedChat) return;

    const config: TransferJobCreate = {
      source_account: sourceAccount,
      source_chat_id: selectedChat.id,
      mode,
      target_type: targetType,
      ...(targetType === 'manual' && targetChatId ? { target_chat_id: targetChatId } : {}),
      ...(dateFromStr ? { date_from: dateFromStr } : {}),
      ...(dateToStr ? { date_to: dateToStr } : {}),
      include_text: includeText,
      include_media: includeMedia,
      ...(maxFileSizeMb ? { max_file_size_mb: Number(maxFileSizeMb) } : {}),
      keyword_whitelist: keywordWhitelist,
      keyword_blacklist: keywordBlacklist,
    };

    createMutation.mutate(config);
  }, [
    sourceAccount, selectedChat, mode, targetType, targetChatId,
    dateFromStr, dateToStr, includeText, includeMedia,
    maxFileSizeMb, keywordWhitelist, keywordBlacklist, createMutation,
  ]);

  const targetLabel = targetType === 'saved_messages'
    ? 'Saved Messages'
    : targetChats.find((c) => c.id === targetChatId)?.title ?? 'Select a chat...';

  return (
    <div className="space-y-4">
      {/* ── FROM → TO cards ─────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
        <AccountCard
          role="from"
          account={sourceAccount}
          onAccountChange={handleSourceAccountChange}
          selectedChat={selectedChat}
          onSelectGroup={() => setModalOpen(true)}
        />

        {/* Arrow */}
        <div className="flex justify-center sm:self-center text-base-content/30 text-2xl font-bold select-none">
          <span className="hidden sm:inline">&rarr;</span>
          <span className="sm:hidden">&darr;</span>
        </div>

        <AccountCard
          role="to"
          account={targetAccount}
          targetType={targetType}
          onTargetTypeChange={(t) => { setTargetType(t); setTargetChatId(undefined); }}
          targetChatTitle={targetType === 'manual' ? targetLabel : undefined}
        />
      </div>

      {/* ── Target chat dropdown (when manual) ──────── */}
      {targetType === 'manual' && (
        <div className="form-control max-w-sm">
          <label className="label"><span className="label-text">Target Chat</span></label>
          {targetChatsLoading ? (
            <div className="flex items-center gap-2 p-2 text-sm text-base-content/60">
              <span className="loading loading-spinner loading-xs" /> Loading chats...
            </div>
          ) : (
            <select
              className="select select-bordered select-sm w-full"
              value={targetChatId ?? ''}
              onChange={(e) => setTargetChatId(e.target.value ? Number(e.target.value) : undefined)}
            >
              <option value="">Select a chat...</option>
              {targetChats.map((chat) => (
                <option key={chat.id} value={chat.id}>{chat.title}</option>
              ))}
            </select>
          )}
        </div>
      )}

      {/* ── Estimate preview ────────────────────────── */}
      {selectedChat && (
        <div className="text-sm">
          {estimateFetching ? (
            <span className="flex items-center gap-2 text-base-content/60">
              <span className="loading loading-spinner loading-xs" /> Estimating messages...
            </span>
          ) : estimateData ? (
            <span className="text-info">
              Approximately {estimateData.count.toLocaleString()} messages
              {estimateData.capped && <span className="text-warning ml-1">(actual count may be higher)</span>}
            </span>
          ) : null}
        </div>
      )}

      {/* ── Preview panel (collapsible) ─────────────── */}
      {selectedChat && (
        <div className="collapse collapse-arrow bg-base-100 border border-base-300">
          <input
            type="checkbox"
            checked={previewOpen}
            onChange={(e) => setPreviewOpen(e.target.checked)}
          />
          <div className="collapse-title text-sm font-medium">
            Message Preview
          </div>
          <div className="collapse-content">
            {previewLoading ? (
              <div className="space-y-2 py-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i} className="skeleton h-4 w-full" />
                ))}
              </div>
            ) : previewMessages.length === 0 ? (
              <p className="text-sm text-base-content/50 py-2">No messages.</p>
            ) : (
              <div className="space-y-1 py-2">
                {previewMessages.map((msg) => (
                  <div key={msg.id} className="text-sm">
                    <span className="font-bold">{msg.sender_name || 'Unknown'}</span>
                    <span className="text-xs text-base-content/50 ml-2">
                      {new Date(msg.date).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                    </span>
                    {msg.text && <p className="line-clamp-1 text-base-content/70">{msg.text}</p>}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Transfer settings ───────────────────────── */}
      <div className="card bg-base-100 shadow-sm border border-base-300">
        <div className="card-body p-4 gap-3">
          <h3 className="card-title text-base">Transfer Settings</h3>

          <div className="flex flex-col lg:flex-row gap-4">
            {/* Left column: mode & filters */}
            <div className="flex-1 space-y-3">
              {/* Mode */}
              <div className="form-control">
                <label className="label"><span className="label-text font-medium">Transfer Mode</span></label>
                <div className="flex gap-4">
                  <label className="label cursor-pointer gap-2">
                    <input type="radio" className="radio radio-primary radio-sm"
                      checked={mode === 'forward'} onChange={() => setMode('forward')} />
                    <div>
                      <span className="label-text">Forward</span>
                      <p className="text-xs text-base-content/50">Shows original sender</p>
                    </div>
                  </label>
                  <label className="label cursor-pointer gap-2">
                    <input type="radio" className="radio radio-primary radio-sm"
                      checked={mode === 'copy'} onChange={() => setMode('copy')} />
                    <div>
                      <span className="label-text">Copy</span>
                      <p className="text-xs text-base-content/50">Sends as you</p>
                    </div>
                  </label>
                </div>
              </div>

              {/* Basic filters */}
              <div className="form-control">
                <label className="label"><span className="label-text font-medium">Content Filters</span></label>
                <div className="flex gap-4 flex-wrap">
                  <label className="label cursor-pointer gap-2">
                    <input type="checkbox" className="checkbox checkbox-sm"
                      checked={includeText} onChange={(e) => setIncludeText(e.target.checked)} />
                    <span className="label-text">Include text</span>
                  </label>
                  <label className="label cursor-pointer gap-2">
                    <input type="checkbox" className="checkbox checkbox-sm"
                      checked={includeMedia} onChange={(e) => setIncludeMedia(e.target.checked)} />
                    <span className="label-text">Include media</span>
                  </label>
                </div>
              </div>

              {/* Advanced filters (collapsible) */}
              <div className="collapse collapse-arrow bg-base-200 rounded-lg">
                <input type="checkbox" checked={showAdvanced} onChange={(e) => setShowAdvanced(e.target.checked)} />
                <div className="collapse-title text-sm font-medium py-2 min-h-0">
                  Advanced Filters
                </div>
                <div className="collapse-content space-y-2">
                  <label className="input input-bordered input-sm flex items-center gap-2 w-40">
                    <input type="number" className="grow w-full" placeholder="No limit" min={0}
                      value={maxFileSizeMb} onChange={(e) => setMaxFileSizeMb(e.target.value)} />
                    <span className="text-sm text-base-content/60">MB</span>
                  </label>
                  <input type="text" className="input input-bordered input-sm w-full"
                    placeholder="Keyword whitelist (comma-separated)"
                    value={keywordWhitelist} onChange={(e) => setKeywordWhitelist(e.target.value)} />
                  <input type="text" className="input input-bordered input-sm w-full"
                    placeholder="Keyword blacklist (comma-separated)"
                    value={keywordBlacklist} onChange={(e) => setKeywordBlacklist(e.target.value)} />
                </div>
              </div>
            </div>

            {/* Right column: calendar (only shown when chat selected) */}
            {selectedChat && (
              <div className="lg:border-l lg:border-base-300 lg:pl-4">
                <label className="label"><span className="label-text font-medium">Date Range</span></label>
                <MessageCalendar
                  account={sourceAccount}
                  chatId={selectedChat.id}
                  month={calendarMonth}
                  onMonthChange={setCalendarMonth}
                  selected={dateRange}
                  onSelect={setDateRange}
                />
              </div>
            )}
          </div>

          {/* Validation error */}
          {validationError && (
            <div className="alert alert-warning text-sm">{validationError}</div>
          )}

          {/* Submit */}
          <div className="card-actions justify-end mt-2">
            <button type="button" className="btn btn-primary" onClick={handleSubmit} disabled={!selectedChat}>
              Start Transfer
            </button>
          </div>
        </div>
      </div>

      {/* ── Modals ──────────────────────────────────── */}
      <ChatSelectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSelect={handleChatSelect}
        account={sourceAccount}
        selectedChatId={selectedChat?.id ?? null}
      />

      <TransferConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={handleConfirm}
        summary={{
          sourceAccount,
          sourceChatTitle: selectedChat?.title ?? 'N/A',
          targetAccount,
          targetLabel,
          mode,
          dateFrom: dateFromStr,
          dateTo: dateToStr,
          includeText,
          includeMedia,
          maxFileSizeMb: maxFileSizeMb || undefined,
          keywordWhitelist: keywordWhitelist || undefined,
          keywordBlacklist: keywordBlacklist || undefined,
          estimateCount: estimateData?.count,
          estimateCapped: estimateData?.capped,
        }}
        isPending={createMutation.isPending}
        error={submitError}
      />
    </div>
  );
}
