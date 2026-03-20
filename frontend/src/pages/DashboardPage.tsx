import TransferBuilder from '../features/dashboard/TransferBuilder';
import TransferProgress from '../features/dashboard/TransferProgress';
import { useTransferStore } from '../stores/transferStore';

export default function DashboardPage() {
  const status = useTransferStore((s) => s.status);

  return (
    <div className="p-4 max-w-5xl mx-auto">
      {status === 'idle' ? <TransferBuilder /> : <TransferProgress />}
    </div>
  );
}
