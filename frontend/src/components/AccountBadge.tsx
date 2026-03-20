import type { AccountInfo } from '../types/api';

interface AccountBadgeProps {
  account: 'A' | 'B';
  info: AccountInfo | null;
}

export default function AccountBadge({ account, info }: AccountBadgeProps) {
  if (info?.is_authorized) {
    const displayName = info.name.length > 12 ? info.name.slice(0, 12) + '...' : info.name;
    return (
      <span className="badge badge-success gap-1 text-xs">
        {account}: {displayName}
      </span>
    );
  }

  return (
    <span className="badge badge-ghost gap-1 text-xs">
      {account}: Not logged in
    </span>
  );
}
