import type { AccountKey, ChatInfo } from '../../types/api';
import { useAuthStore } from '../../stores/authStore';

const ACCOUNT_OPTIONS: { key: AccountKey; label: string }[] = [
  { key: 'account_a', label: 'Account A' },
  { key: 'account_b', label: 'Account B' },
];

interface AccountCardProps {
  role: 'from' | 'to';
  account: AccountKey;
  onAccountChange?: (account: AccountKey) => void;
  selectedChat?: ChatInfo | null;
  onSelectGroup?: () => void;
  disabled?: boolean;
  // TO-specific props
  targetType?: 'saved_messages' | 'manual';
  onTargetTypeChange?: (type: 'saved_messages' | 'manual') => void;
  targetChatTitle?: string;
}

export default function AccountCard({
  role,
  account,
  onAccountChange,
  selectedChat,
  onSelectGroup,
  disabled = false,
  targetType,
  onTargetTypeChange,
  targetChatTitle,
}: AccountCardProps) {
  const accountA = useAuthStore((s) => s.accountA);
  const accountB = useAuthStore((s) => s.accountB);
  const info = account === 'account_a' ? accountA : accountB;

  return (
    <div className="card bg-base-100 shadow-sm border border-base-300 flex-1 min-w-[250px]">
      <div className="card-body p-4 gap-3">
        {/* Label */}
        <div className="flex items-center gap-2">
          <span className={`badge ${role === 'from' ? 'badge-primary' : 'badge-secondary'} badge-sm font-bold`}>
            {role === 'from' ? 'FROM' : 'TO'}
          </span>
          {info && (
            <span className="text-xs text-base-content/50 truncate">
              {info.name || info.phone}
            </span>
          )}
        </div>

        {/* Account selector */}
        <select
          className="select select-bordered select-sm w-full"
          value={account}
          onChange={(e) => onAccountChange?.(e.target.value as AccountKey)}
          disabled={disabled || !onAccountChange}
        >
          {ACCOUNT_OPTIONS.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* FROM: group selection */}
        {role === 'from' && (
          <button
            type="button"
            className="btn btn-outline btn-sm w-full justify-start gap-2"
            onClick={onSelectGroup}
            disabled={disabled}
          >
            {selectedChat ? (
              <>
                <span className="truncate">{selectedChat.title}</span>
                <span className="badge badge-ghost badge-xs ml-auto">{selectedChat.type}</span>
              </>
            ) : (
              <span className="text-base-content/50">Select group...</span>
            )}
          </button>
        )}

        {/* TO: target type */}
        {role === 'to' && (
          <div className="space-y-1">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                className="radio radio-sm radio-secondary"
                checked={targetType === 'saved_messages'}
                onChange={() => onTargetTypeChange?.('saved_messages')}
                disabled={disabled}
              />
              <span className="label-text text-sm">Saved Messages</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                className="radio radio-sm radio-secondary"
                checked={targetType === 'manual'}
                onChange={() => onTargetTypeChange?.('manual')}
                disabled={disabled}
              />
              <span className="label-text text-sm">Specific Chat</span>
            </label>
            {targetType === 'manual' && targetChatTitle && (
              <div className="text-xs text-base-content/60 pl-6 truncate">
                {targetChatTitle}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
