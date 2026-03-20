import { useRef, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useVirtualizer } from '@tanstack/react-virtual';
import { listChats } from '../../api/chats';
import { useDebounce } from '../../hooks/useDebounce';
import type { AccountKey, ChatInfo } from '../../types/api';

const CHAT_TYPE_EMOJI: Record<ChatInfo['type'], string> = {
  user: '\u{1F464}',
  group: '\u{1F465}',
  supergroup: '\u{1F465}',
  channel: '\u{1F4E2}',
};

type SortOption = 'recent' | 'name' | 'unread';

interface ChatListProps {
  account: AccountKey;
  onSelectChat: (chat: ChatInfo) => void;
  selectedChatId: number | null;
}

function formatRelativeDate(isoDate: string | null): string {
  if (!isoDate) return '';
  const date = new Date(isoDate);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    });
  }
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

const PAGE_SIZE = 50;

export default function ChatList({
  account,
  onSelectChat,
  selectedChatId,
}: ChatListProps) {
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState<SortOption>('recent');
  const debouncedSearch = useDebounce(search, 300);

  const { data, fetchNextPage, hasNextPage, isFetchingNextPage, isLoading } =
    useInfiniteQuery({
      queryKey: ['chats', account, debouncedSearch, sort],
      queryFn: ({ pageParam = 0 }) =>
        listChats(account, {
          limit: PAGE_SIZE,
          offset: pageParam as number,
          search: debouncedSearch || undefined,
          sort,
        }),
      getNextPageParam: (lastPage, allPages) =>
        lastPage.has_more ? allPages.length * PAGE_SIZE : undefined,
      initialPageParam: 0,
    });

  const chats = data?.pages.flatMap((p) => p.chats) ?? [];

  const parentRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: chats.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 5,
  });

  // Detect scroll to bottom for infinite loading
  function handleScroll() {
    const el = parentRef.current;
    if (!el || !hasNextPage || isFetchingNextPage) return;
    const { scrollTop, scrollHeight, clientHeight } = el;
    if (scrollHeight - scrollTop - clientHeight < 100) {
      void fetchNextPage();
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Search + Sort controls */}
      <div className="p-3 space-y-2 border-b border-base-300">
        <input
          type="text"
          className="input input-bordered input-sm w-full"
          placeholder="Search chats..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="select select-bordered select-sm w-full"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOption)}
        >
          <option value="recent">Recent</option>
          <option value="name">Name</option>
          <option value="unread">Unread</option>
        </select>
      </div>

      {/* Chat list */}
      {isLoading ? (
        <div className="flex-1 p-3 space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-2">
              <div className="skeleton h-10 w-10 rounded-full shrink-0" />
              <div className="flex-1 space-y-1">
                <div className="skeleton h-4 w-3/4" />
                <div className="skeleton h-3 w-1/2" />
              </div>
            </div>
          ))}
        </div>
      ) : chats.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-base-content/50 p-4">
          {debouncedSearch ? 'No chats match your search.' : 'No chats found.'}
        </div>
      ) : (
        <div
          ref={parentRef}
          className="flex-1 overflow-auto"
          onScroll={handleScroll}
        >
          <div
            className="relative w-full"
            style={{ height: `${virtualizer.getTotalSize()}px` }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => {
              const chat = chats[virtualRow.index];
              if (!chat) return null;
              const isSelected = chat.id === selectedChatId;

              return (
                <div
                  key={chat.id}
                  data-index={virtualRow.index}
                  ref={virtualizer.measureElement}
                  className={`absolute top-0 left-0 w-full cursor-pointer hover:bg-base-200 transition-colors px-3 py-2 ${
                    isSelected ? 'bg-base-200' : ''
                  }`}
                  style={{
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                  onClick={() => onSelectChat(chat)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg shrink-0" aria-hidden="true">
                      {CHAT_TYPE_EMOJI[chat.type]}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`truncate ${isSelected ? 'font-bold' : ''}`}
                        >
                          {chat.title}
                        </span>
                        {chat.unread_count > 0 && (
                          <span className="badge badge-primary badge-sm shrink-0">
                            {chat.unread_count}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-base-content/50">
                        {formatRelativeDate(chat.last_message_date)}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {isFetchingNextPage && (
            <div className="flex justify-center py-3">
              <span className="loading loading-spinner loading-sm" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
