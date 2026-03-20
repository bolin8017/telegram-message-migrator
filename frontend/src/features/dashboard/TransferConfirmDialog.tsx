import { useEffect, useRef } from 'react';
import type { AccountKey, TransferMode } from '../../types/api';

interface TransferSummary {
  sourceAccount: AccountKey;
  sourceChatTitle: string;
  targetAccount: AccountKey;
  targetLabel: string;
  mode: TransferMode;
  dateFrom?: string;
  dateTo?: string;
  includeText: boolean;
  includeMedia: boolean;
  maxFileSizeMb?: string;
  keywordWhitelist?: string;
  keywordBlacklist?: string;
  estimateCount?: number;
  estimateCapped?: boolean;
}

interface TransferConfirmDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  summary: TransferSummary;
  isPending: boolean;
  error: string | null;
}

export default function TransferConfirmDialog({
  open,
  onClose,
  onConfirm,
  summary,
  isPending,
  error,
}: TransferConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    if (open) dialogRef.current?.showModal();
    else dialogRef.current?.close();
  }, [open]);

  const s = summary;

  return (
    <dialog ref={dialogRef} className="modal" onClose={onClose}>
      <div className="modal-box">
        <h3 className="font-bold text-lg">Confirm Transfer</h3>
        <div className="py-4 space-y-2 text-sm">
          <p><span className="font-medium">From:</span> {s.sourceChatTitle} ({s.sourceAccount === 'account_a' ? 'Account A' : 'Account B'})</p>
          <p><span className="font-medium">To:</span> {s.targetLabel} ({s.targetAccount === 'account_a' ? 'Account A' : 'Account B'})</p>
          <p><span className="font-medium">Mode:</span> {s.mode === 'forward' ? 'Forward (shows original sender)' : 'Copy (sends as you)'}</p>
          {(s.dateFrom || s.dateTo) && (
            <p><span className="font-medium">Date range:</span> {s.dateFrom || 'start'} to {s.dateTo || 'now'}</p>
          )}
          <p>
            <span className="font-medium">Filters:</span>{' '}
            {s.includeText ? 'Text' : ''}{s.includeText && s.includeMedia ? ' + ' : ''}{s.includeMedia ? 'Media' : ''}
            {!s.includeText && !s.includeMedia ? 'None' : ''}
            {s.maxFileSizeMb ? ` (max ${s.maxFileSizeMb} MB)` : ''}
          </p>
          {s.keywordWhitelist && <p><span className="font-medium">Whitelist:</span> {s.keywordWhitelist}</p>}
          {s.keywordBlacklist && <p><span className="font-medium">Blacklist:</span> {s.keywordBlacklist}</p>}
          {s.estimateCount != null && (
            <p className="text-info">
              ~{s.estimateCount.toLocaleString()} messages to transfer
              {s.estimateCapped && <span className="text-warning ml-1">(may be higher)</span>}
            </p>
          )}
        </div>

        {error && <div className="alert alert-error text-sm mb-2">{error}</div>}

        <div className="modal-action">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={isPending}>Cancel</button>
          <button type="button" className="btn btn-primary" onClick={onConfirm} disabled={isPending}>
            {isPending && <span className="loading loading-spinner loading-sm" />}
            Start Transfer
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button type="submit">close</button>
      </form>
    </dialog>
  );
}
