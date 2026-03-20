import { useState } from 'react';
import { sendCode, submitCode, submit2FA } from '../../api/auth';
import { ApiError } from '../../api/client';
import { useAuthStore } from '../../stores/authStore';
import FloodWaitTimer from '../../components/FloodWaitTimer';
import type { AccountKey } from '../../types/api';

type LoginPhase = 'phone' | 'code' | '2fa';

interface LoginStepProps {
  account: AccountKey;
  onNext: () => void;
}

const ACCOUNT_LABELS: Record<AccountKey, string> = {
  account_a: 'Account A (Source)',
  account_b: 'Account B (Destination)',
};

export default function LoginStep({ account, onNext }: LoginStepProps) {
  const [phase, setPhase] = useState<LoginPhase>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [floodWaitSeconds, setFloodWaitSeconds] = useState<number | null>(null);

  const setAccount = useAuthStore((s) => s.setAccount);

  async function handleSendCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await sendCode(account, phone);
      setPhase('code');
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429 && err.waitSeconds) {
          setFloodWaitSeconds(err.waitSeconds);
        } else if (err.status === 422) {
          setError('Invalid phone number');
        } else if (err.status === 409) {
          setError('Login already in progress for this number');
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

  async function handleSubmitCode(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await submitCode(account, code);
      if (result.status === '2fa_required') {
        setPhase('2fa');
      } else if (result.status === 'success' && result.user) {
        setAccount(account, result.user);
        onNext();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429 && err.waitSeconds) {
          setFloodWaitSeconds(err.waitSeconds);
        } else if (err.status === 422) {
          setError(err.detail.includes('expired') ? 'Code expired' : 'Invalid code');
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

  async function handleSubmit2FA(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const result = await submit2FA(account, password);
      if (result.status === 'success' && result.user) {
        setAccount(account, result.user);
        onNext();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429 && err.waitSeconds) {
          setFloodWaitSeconds(err.waitSeconds);
        } else if (err.status === 422) {
          setError('Incorrect 2FA password');
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

  if (floodWaitSeconds !== null) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold">Login — {ACCOUNT_LABELS[account]}</h2>
        </div>
        <FloodWaitTimer
          seconds={floodWaitSeconds}
          onExpire={() => setFloodWaitSeconds(null)}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold">Login — {ACCOUNT_LABELS[account]}</h2>
        <p className="mt-1 text-base-content/70">
          {phase === 'phone' && 'Enter the phone number for this Telegram account.'}
          {phase === 'code' && 'Enter the code sent to your Telegram app.'}
          {phase === '2fa' && 'Enter your two-factor authentication password.'}
        </p>
      </div>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      )}

      {phase === 'phone' && (
        <form onSubmit={handleSendCode} className="space-y-4">
          <div className="form-control">
            <label className="label" htmlFor={`phone-${account}`}>
              <span className="label-text">Phone Number</span>
            </label>
            <input
              id={`phone-${account}`}
              type="tel"
              inputMode="tel"
              className="input input-bordered w-full"
              placeholder="+1234567890"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              disabled={loading}
              required
            />
          </div>
          <div className="card-actions justify-end pt-2">
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading && <span className="loading loading-spinner loading-sm" />}
              Send Code
            </button>
          </div>
        </form>
      )}

      {phase === 'code' && (
        <form onSubmit={handleSubmitCode} className="space-y-4">
          <div className="form-control">
            <label className="label" htmlFor={`code-${account}`}>
              <span className="label-text">Verification Code</span>
            </label>
            <input
              id={`code-${account}`}
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              className="input input-bordered w-full"
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              disabled={loading}
              required
            />
          </div>
          <div className="card-actions justify-end pt-2">
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading && <span className="loading loading-spinner loading-sm" />}
              Verify Code
            </button>
          </div>
        </form>
      )}

      {phase === '2fa' && (
        <form onSubmit={handleSubmit2FA} className="space-y-4">
          <div className="form-control">
            <label className="label" htmlFor={`password-${account}`}>
              <span className="label-text">2FA Password</span>
            </label>
            <input
              id={`password-${account}`}
              type="password"
              className="input input-bordered w-full"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
          </div>
          <div className="card-actions justify-end pt-2">
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading && <span className="loading loading-spinner loading-sm" />}
              Submit Password
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
