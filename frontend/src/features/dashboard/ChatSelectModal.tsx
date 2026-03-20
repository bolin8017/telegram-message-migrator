import { useEffect, useRef, useState } from 'react';
import ChatList from './ChatList';
import type { AccountKey, ChatInfo } from '../../types/api';

interface ChatSelectModalProps {
  open: boolean;
  onClose: () => void;
  onSelect: (chat: ChatInfo) => void;
  account: AccountKey;
  selectedChatId: number | null;
}

export default function ChatSelectModal({
  open,
  onClose,
  onSelect,
  account,
  selectedChatId,
}: ChatSelectModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [pendingChat, setPendingChat] = useState<ChatInfo | null>(null);

  useEffect(() => {
    if (open) {
      setPendingChat(null);
      dialogRef.current?.showModal();
    } else {
      dialogRef.current?.close();
    }
  }, [open]);

  function handleConfirm() {
    if (pendingChat) {
      onSelect(pendingChat);
    }
    onClose();
  }

  return (
    <dialog
      ref={dialogRef}
      className="modal modal-bottom sm:modal-middle"
      onClose={onClose}
    >
      <div className="modal-box h-[70vh] sm:h-[70vh] max-w-2xl flex flex-col p-0">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-base-300">
          <h3 className="font-bold text-lg">Select Source Chat</h3>
          <button type="button" className="btn btn-ghost btn-sm btn-circle" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* Chat list fills remaining space */}
        <div className="flex-1 overflow-hidden">
          <ChatList
            account={account}
            onSelectChat={setPendingChat}
            selectedChatId={pendingChat?.id ?? selectedChatId}
          />
        </div>

        {/* Footer with confirm */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-base-300">
          <span className="text-sm text-base-content/60 truncate">
            {pendingChat ? pendingChat.title : 'No chat selected'}
          </span>
          <div className="flex gap-2">
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={handleConfirm}
              disabled={!pendingChat}
            >
              Select
            </button>
          </div>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button type="submit">close</button>
      </form>
    </dialog>
  );
}
