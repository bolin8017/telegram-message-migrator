import { describe, it, expect, beforeEach } from 'vitest';
import { useAuthStore } from '../../src/stores/authStore';

beforeEach(() => {
  useAuthStore.setState(useAuthStore.getInitialState());
});

describe('authStore', () => {
  it('starts with null accounts', () => {
    const state = useAuthStore.getState();
    expect(state.accountA).toBeNull();
    expect(state.accountB).toBeNull();
  });

  it('sets account_a info', () => {
    const info = {
      phone: '+1234',
      name: 'Test',
      username: null,
      is_authorized: true,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_a', info);
    expect(useAuthStore.getState().accountA).toEqual(info);
    expect(useAuthStore.getState().accountB).toBeNull();
  });

  it('sets account_b info', () => {
    const info = {
      phone: '+5678',
      name: 'Other',
      username: 'other',
      is_authorized: true,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_b', info);
    expect(useAuthStore.getState().accountB).toEqual(info);
    expect(useAuthStore.getState().accountA).toBeNull();
  });

  it('clears account by setting null', () => {
    const info = {
      phone: '+1234',
      name: 'Test',
      username: null,
      is_authorized: true,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_a', info);
    useAuthStore.getState().setAccount('account_a', null);
    expect(useAuthStore.getState().accountA).toBeNull();
  });

  it('sets credentialsReady', () => {
    expect(useAuthStore.getState().credentialsReady).toBe(false);
    useAuthStore.getState().setCredentialsReady(true);
    expect(useAuthStore.getState().credentialsReady).toBe(true);
  });

  it('sets loading', () => {
    expect(useAuthStore.getState().loading).toBe(false);
    useAuthStore.getState().setLoading(true);
    expect(useAuthStore.getState().loading).toBe(true);
  });

  it('isFullyAuthenticated returns false when no accounts', () => {
    expect(useAuthStore.getState().isFullyAuthenticated()).toBe(false);
  });

  it('isFullyAuthenticated returns false when only account_a authorized', () => {
    const info = {
      phone: '+1234',
      name: 'Test',
      username: null,
      is_authorized: true,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_a', info);
    expect(useAuthStore.getState().isFullyAuthenticated()).toBe(false);
  });

  it('isFullyAuthenticated returns false when account not authorized', () => {
    const infoA = {
      phone: '+1234',
      name: 'Test',
      username: null,
      is_authorized: true,
      session_expired: false,
    };
    const infoB = {
      phone: '+5678',
      name: 'Other',
      username: null,
      is_authorized: false,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_a', infoA);
    useAuthStore.getState().setAccount('account_b', infoB);
    expect(useAuthStore.getState().isFullyAuthenticated()).toBe(false);
  });

  it('isFullyAuthenticated returns true when both authorized', () => {
    const info = {
      phone: '+1234',
      name: 'Test',
      username: null,
      is_authorized: true,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_a', info);
    useAuthStore.getState().setAccount('account_b', info);
    expect(useAuthStore.getState().isFullyAuthenticated()).toBe(true);
  });

  it('reset clears all state', () => {
    const info = {
      phone: '+1234',
      name: 'Test',
      username: null,
      is_authorized: true,
      session_expired: false,
    };
    useAuthStore.getState().setAccount('account_a', info);
    useAuthStore.getState().setCredentialsReady(true);
    useAuthStore.getState().setLoading(true);
    useAuthStore.getState().reset();
    expect(useAuthStore.getState().accountA).toBeNull();
    expect(useAuthStore.getState().accountB).toBeNull();
    expect(useAuthStore.getState().credentialsReady).toBe(false);
    expect(useAuthStore.getState().loading).toBe(false);
  });
});
