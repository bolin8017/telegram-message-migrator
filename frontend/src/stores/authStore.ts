import { create } from 'zustand';
import type { AccountInfo, AccountKey } from '../types/api';

interface AuthState {
  accountA: AccountInfo | null;
  accountB: AccountInfo | null;
  credentialsReady: boolean;
  loading: boolean;
  setAccount: (key: AccountKey, info: AccountInfo | null) => void;
  setCredentialsReady: (ready: boolean) => void;
  setLoading: (loading: boolean) => void;
  reset: () => void;
  isFullyAuthenticated: () => boolean;
}

const initialState = {
  accountA: null as AccountInfo | null,
  accountB: null as AccountInfo | null,
  credentialsReady: false,
  loading: false,
};

export const useAuthStore = create<AuthState>()((set, get) => ({
  ...initialState,
  setAccount: (key, info) =>
    set(key === 'account_a' ? { accountA: info } : { accountB: info }),
  setCredentialsReady: (ready) => set({ credentialsReady: ready }),
  setLoading: (loading) => set({ loading }),
  reset: () => set(initialState),
  isFullyAuthenticated: () => {
    const { accountA, accountB } = get();
    return accountA?.is_authorized === true && accountB?.is_authorized === true;
  },
}));
