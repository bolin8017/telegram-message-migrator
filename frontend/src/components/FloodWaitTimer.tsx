import { useEffect, useRef, useState } from 'react';

interface FloodWaitTimerProps {
  seconds: number;
  onExpire: () => void;
}

export default function FloodWaitTimer({ seconds, onExpire }: FloodWaitTimerProps) {
  const [remaining, setRemaining] = useState(seconds);
  const onExpireRef = useRef(onExpire);
  onExpireRef.current = onExpire;

  useEffect(() => {
    const timer = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          onExpireRef.current();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const mins = Math.floor(remaining / 60);
  const secs = remaining % 60;

  return (
    <div className="alert alert-warning">
      <span>
        Rate limited by Telegram. Please wait {mins}:{secs.toString().padStart(2, '0')}
      </span>
    </div>
  );
}
