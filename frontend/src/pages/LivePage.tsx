import LiveMonitor from '../features/live/LiveMonitor';
import EventFeed from '../features/live/EventFeed';

export default function LivePage() {
  return (
    <div className="flex flex-col gap-4 p-4 h-full">
      <LiveMonitor />
      <EventFeed />
    </div>
  );
}
