import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

export default function CompleteStep() {
  const navigate = useNavigate();
  const accountA = useAuthStore((s) => s.accountA);
  const accountB = useAuthStore((s) => s.accountB);

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h2 className="text-2xl font-bold">Setup Complete!</h2>
        <p className="mt-2 text-base-content/70">
          Both accounts are connected and ready to use.
        </p>
      </div>

      <div className="divider" />

      <div className="space-y-3">
        {accountA && (
          <p className="text-success">
            &#10003; {accountA.name} ({accountA.phone}) — Account A
          </p>
        )}
        {accountB && (
          <p className="text-success">
            &#10003; {accountB.name} ({accountB.phone}) — Account B
          </p>
        )}
      </div>

      <div className="card-actions justify-end pt-4">
        <button className="btn btn-primary" onClick={() => navigate('/dashboard')}>
          Go to Dashboard
        </button>
      </div>
    </div>
  );
}
