import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { logout } from '../../api/auth';
import { deleteUserData } from '../../api/user';
import { ApiError } from '../../api/client';
import { useAuthStore } from '../../stores/authStore';
import { useTransferStore } from '../../stores/transferStore';
import { useLiveStore } from '../../stores/liveStore';
import { useTheme } from '../../hooks/useTheme';
import type { AccountKey } from '../../types/api';

// ── Session Info Section ─────────────────────────────

function AccountRow({
  label,
  accountKey,
}: {
  label: string;
  accountKey: AccountKey;
}) {
  const info = useAuthStore((s) =>
    accountKey === 'account_a' ? s.accountA : s.accountB,
  );
  const setAccount = useAuthStore((s) => s.setAccount);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogout() {
    setError(null);
    setLoading(true);
    try {
      await logout(accountKey);
      setAccount(accountKey, null);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('Logout failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  const isLoggedIn = info?.is_authorized === true;

  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-3">
        <span
          className={`badge badge-xs ${isLoggedIn ? 'badge-success' : 'badge-ghost'}`}
        />
        <div>
          <span className="font-medium">{label}</span>
          {isLoggedIn ? (
            <p className="text-sm text-base-content/70">
              {info.name} &middot; {info.phone}
            </p>
          ) : (
            <p className="text-sm text-base-content/50">Not logged in</p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        {error && <span className="text-xs text-error">{error}</span>}
        {isLoggedIn && (
          <button
            className="btn btn-outline btn-sm"
            onClick={handleLogout}
            disabled={loading}
          >
            {loading && (
              <span className="loading loading-spinner loading-xs" />
            )}
            Logout
          </button>
        )}
      </div>
    </div>
  );
}

// ── Theme Section ────────────────────────────────────

function ThemeSection() {
  const { theme, toggle } = useTheme();

  return (
    <div className="flex items-center justify-between">
      <div>
        <span className="font-medium">Theme</span>
        <p className="text-sm text-base-content/70 capitalize">{theme}</p>
      </div>
      <label className="swap swap-rotate">
        <input
          type="checkbox"
          checked={theme === 'dark'}
          onChange={toggle}
          aria-label="Toggle theme"
        />

        {/* Sun icon — shown when dark (checked) */}
        <svg
          className="swap-on h-6 w-6 fill-current"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
        >
          <path d="M21.64 13a1 1 0 0 0-1.05-.14 8.05 8.05 0 0 1-3.37.73A8.15 8.15 0 0 1 9.08 5.49a8.59 8.59 0 0 1 .25-2A1 1 0 0 0 8 2.36a10.14 10.14 0 1 0 14 11.69 1 1 0 0 0-.36-1.05Z" />
        </svg>

        {/* Moon icon — shown when light (unchecked) */}
        <svg
          className="swap-off h-6 w-6 fill-current"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
        >
          <path d="M5.64 17l-.71.71a1 1 0 0 0 0 1.41 1 1 0 0 0 1.41 0l.71-.71A1 1 0 0 0 5.64 17ZM5 12a1 1 0 0 0-1-1H3a1 1 0 0 0 0 2h1a1 1 0 0 0 1-1Zm7-7a1 1 0 0 0 1-1V3a1 1 0 0 0-2 0v1a1 1 0 0 0 1 1ZM5.64 7.05a1 1 0 0 0 .7.29 1 1 0 0 0 .71-.29 1 1 0 0 0 0-1.41l-.71-.71a1 1 0 1 0-1.41 1.41l.71.71Zm12.02 10.66-.71.71a1 1 0 0 0 0 1.41 1 1 0 0 0 1.41 0l.71-.71a1 1 0 0 0-1.41-1.41ZM21 11h-1a1 1 0 0 0 0 2h1a1 1 0 0 0 0-2Zm-9 8a1 1 0 0 0-1 1v1a1 1 0 0 0 2 0v-1a1 1 0 0 0-1-1Zm7.36-2.95a1 1 0 0 0-1.41 0 1 1 0 0 0 0 1.41l.71.71a1 1 0 0 0 1.41 0 1 1 0 0 0 0-1.41l-.71-.71ZM12 6.5A5.5 5.5 0 1 0 17.5 12 5.51 5.51 0 0 0 12 6.5Zm0 9A3.5 3.5 0 1 1 15.5 12 3.5 3.5 0 0 1 12 15.5Z" />
        </svg>
      </label>
    </div>
  );
}

// ── Danger Zone Section ──────────────────────────────

function DangerZone() {
  const navigate = useNavigate();
  const authReset = useAuthStore((s) => s.reset);
  const transferReset = useTransferStore((s) => s.reset);
  const liveReset = useLiveStore((s) => s.reset);

  const [modalOpen, setModalOpen] = useState(false);
  const [confirmText, setConfirmText] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function openModal() {
    setConfirmText('');
    setError(null);
    setModalOpen(true);
  }

  function closeModal() {
    if (!loading) {
      setModalOpen(false);
    }
  }

  async function handleDelete() {
    setError(null);
    setLoading(true);
    try {
      await deleteUserData();
      authReset();
      transferReset();
      liveReset();
      setModalOpen(false);
      navigate('/');
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to delete data. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  }

  const canConfirm = confirmText === 'DELETE';

  return (
    <>
      <div className="alert alert-error">
        <div className="flex w-full items-center justify-between">
          <div>
            <h3 className="font-bold">Delete All My Data</h3>
            <p className="text-sm">
              Permanently remove all your data from this server.
            </p>
          </div>
          <button className="btn btn-error btn-sm" onClick={openModal}>
            Delete All My Data
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      <dialog
        className={`modal ${modalOpen ? 'modal-open' : ''}`}
        onClick={closeModal}
      >
        <div className="modal-box" onClick={(e) => e.stopPropagation()}>
          <h3 className="text-lg font-bold">Confirm Data Deletion</h3>

          <p className="py-4">
            This will permanently delete all your data:
          </p>

          <ul className="list-disc list-inside space-y-1 text-sm text-base-content/80 pb-4">
            <li>Cancel active transfers</li>
            <li>Stop live forwarding</li>
            <li>Log out both Telegram accounts</li>
            <li>Delete all stored credentials and sessions</li>
            <li>Clear your browser session</li>
          </ul>

          <div className="form-control">
            <label className="label" htmlFor="confirm-delete-input">
              <span className="label-text">
                Type <strong>DELETE</strong> to confirm
              </span>
            </label>
            <input
              id="confirm-delete-input"
              type="text"
              className="input input-bordered w-full"
              placeholder="DELETE"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              disabled={loading}
              autoComplete="off"
            />
          </div>

          {error && (
            <div className="alert alert-error mt-4">
              <span>{error}</span>
            </div>
          )}

          <div className="modal-action">
            <button
              className="btn"
              onClick={closeModal}
              disabled={loading}
            >
              Cancel
            </button>
            <button
              className="btn btn-error"
              onClick={handleDelete}
              disabled={!canConfirm || loading}
            >
              {loading && (
                <span className="loading loading-spinner loading-sm" />
              )}
              Confirm Delete
            </button>
          </div>
        </div>
      </dialog>
    </>
  );
}

// ── Main Panel ───────────────────────────────────────

export default function SettingsPanel() {
  return (
    <div className="space-y-8">
      {/* Session Info */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Account Sessions</h2>
        <div className="card bg-base-200">
          <div className="card-body py-3 divide-y divide-base-300">
            <AccountRow label="Account A (Source)" accountKey="account_a" />
            <AccountRow
              label="Account B (Destination)"
              accountKey="account_b"
            />
          </div>
        </div>
      </section>

      {/* Theme */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Appearance</h2>
        <div className="card bg-base-200">
          <div className="card-body py-4">
            <ThemeSection />
          </div>
        </div>
      </section>

      {/* Danger Zone */}
      <section>
        <h2 className="text-lg font-semibold mb-3">Danger Zone</h2>
        <DangerZone />
      </section>
    </div>
  );
}
