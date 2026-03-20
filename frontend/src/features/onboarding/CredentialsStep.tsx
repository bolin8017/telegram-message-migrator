import { useState } from 'react';
import { setupCredentials } from '../../api/setup';
import { useAuthStore } from '../../stores/authStore';
import { ApiError } from '../../api/client';

interface CredentialsStepProps {
  onNext: () => void;
}

export default function CredentialsStep({ onNext }: CredentialsStepProps) {
  const [apiId, setApiId] = useState('');
  const [apiHash, setApiHash] = useState('');
  const [showHash, setShowHash] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setCredentialsReady = useAuthStore((s) => s.setCredentialsReady);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const parsedId = Number(apiId);
    if (!Number.isInteger(parsedId) || parsedId <= 0) {
      setError('API ID must be a positive integer.');
      return;
    }
    if (!apiHash.trim()) {
      setError('API Hash is required.');
      return;
    }

    setLoading(true);
    try {
      await setupCredentials(parsedId, apiHash.trim());
      setCredentialsReady(true);
      onNext();
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setError('Server is at capacity. Please try again later.');
        } else {
          setError(err.detail);
        }
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">API Credentials</h2>
        <p className="mt-1 text-base-content/70">
          You need a Telegram API ID and Hash to connect your accounts.
        </p>
      </div>

      <div className="alert alert-info">
        <div>
          <h3 className="font-semibold mb-2">How to get your credentials</h3>
          <ol className="list-decimal list-inside space-y-1 text-sm">
            <li>
              Open{' '}
              <a
                href="https://my.telegram.org"
                target="_blank"
                rel="noopener noreferrer"
                className="link font-semibold"
              >
                my.telegram.org
              </a>{' '}
              in your browser
            </li>
            <li>Log in with your phone number</li>
            <li>
              Go to <strong>"API development tools"</strong>
            </li>
            <li>Create an application (any name and short name will do)</li>
            <li>
              Copy the <strong>App api_id</strong> and{' '}
              <strong>App api_hash</strong> values into the form below
            </li>
          </ol>
        </div>
      </div>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="form-control">
          <label className="label" htmlFor="api-id">
            <span className="label-text">API ID</span>
          </label>
          <input
            id="api-id"
            type="number"
            className="input input-bordered w-full"
            placeholder="e.g. 12345678"
            value={apiId}
            onChange={(e) => setApiId(e.target.value)}
            disabled={loading}
            required
          />
        </div>

        <div className="form-control">
          <label className="label" htmlFor="api-hash">
            <span className="label-text">API Hash</span>
          </label>
          <div className="join w-full">
            <input
              id="api-hash"
              type={showHash ? 'text' : 'password'}
              className="input input-bordered join-item w-full"
              placeholder="e.g. a1b2c3d4e5f6..."
              value={apiHash}
              onChange={(e) => setApiHash(e.target.value)}
              disabled={loading}
              required
            />
            <button
              type="button"
              className="btn join-item"
              onClick={() => setShowHash(!showHash)}
            >
              {showHash ? 'Hide' : 'Show'}
            </button>
          </div>
        </div>

        <div className="card-actions justify-end pt-2">
          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
          >
            {loading && <span className="loading loading-spinner loading-sm" />}
            Continue
          </button>
        </div>
      </form>
    </div>
  );
}
