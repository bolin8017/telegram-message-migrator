import { useMemo } from 'react';
import { DayPicker } from 'react-day-picker';
import { useQuery } from '@tanstack/react-query';
import { getMessageDates, getDateRange } from '../../api/chats';
import type { AccountKey } from '../../types/api';
import 'react-day-picker/style.css';

interface MessageCalendarProps {
  account: AccountKey;
  chatId: number;
  month: Date;
  onMonthChange: (month: Date) => void;
  selected: { from: Date | undefined; to: Date | undefined };
  onSelect: (range: { from: Date | undefined; to: Date | undefined }) => void;
  disabled?: boolean;
}

export default function MessageCalendar({
  account,
  chatId,
  month,
  onMonthChange,
  selected,
  onSelect,
  disabled = false,
}: MessageCalendarProps) {
  const year = month.getFullYear();
  const monthNum = month.getMonth() + 1;

  // Fetch date range (earliest/latest)
  const { data: dateRange } = useQuery({
    queryKey: ['dateRange', account, chatId],
    queryFn: () => getDateRange(account, chatId),
    staleTime: 10 * 60 * 1000,
  });

  // Fetch message dates for current month
  const { data: messageDatesData, isLoading } = useQuery({
    queryKey: ['messageDates', account, chatId, year, monthNum],
    queryFn: () => getMessageDates(account, chatId, year, monthNum),
    staleTime: 10 * 60 * 1000,
  });

  // Convert ISO strings to a Set for fast lookup
  const datesWithMessages = useMemo(() => {
    return new Set(messageDatesData?.dates ?? []);
  }, [messageDatesData]);

  // Determine navigable range from dateRange
  const startMonth = dateRange?.earliest ? new Date(dateRange.earliest + 'T00:00:00') : undefined;
  const endMonth = dateRange?.latest ? new Date(dateRange.latest + 'T00:00:00') : undefined;

  // Matcher: day has messages
  const hasMessages = (day: Date) => {
    const key = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`;
    return datesWithMessages.has(key);
  };

  return (
    <div className="relative">
      {isLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-base-100/50 z-10">
          <span className="loading loading-spinner loading-md" />
        </div>
      )}
      <DayPicker
        mode="range"
        selected={selected}
        onSelect={(range) => onSelect({ from: range?.from, to: range?.to })}
        month={month}
        onMonthChange={onMonthChange}
        disabled={(day) => isLoading || !hasMessages(day)}
        modifiers={{ hasMessages }}
        modifiersClassNames={{ hasMessages: 'rdp-has-messages' }}
        startMonth={startMonth}
        endMonth={endMonth}
        captionLayout="dropdown"
      />
      {/* Clear range button */}
      {(selected.from || selected.to) && (
        <button
          type="button"
          className="btn btn-ghost btn-xs mt-1"
          onClick={() => onSelect({ from: undefined, to: undefined })}
          disabled={disabled}
        >
          Clear date range
        </button>
      )}
    </div>
  );
}
