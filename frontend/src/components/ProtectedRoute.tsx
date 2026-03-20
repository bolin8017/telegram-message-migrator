import { useEffect } from 'react';
import { Navigate, Outlet } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { getAuthStatus } from '../api/auth';
import { useAuthStore } from '../stores/authStore';
import LoadingSpinner from './LoadingSpinner';

export default function ProtectedRoute() {
  const setAccount = useAuthStore((s) => s.setAccount);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['authStatus'],
    queryFn: getAuthStatus,
    retry: 1,
    staleTime: 30_000,
  });

  // Sync server auth status into the Zustand store
  useEffect(() => {
    if (data) {
      setAccount('account_a', data.account_a ?? null);
      setAccount('account_b', data.account_b ?? null);
    }
  }, [data, setAccount]);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  // API failure: show error instead of redirecting authenticated users
  if (isError) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="alert alert-error max-w-md">
          <div>
            <p className="font-medium">Connection error</p>
            <p className="text-sm">Unable to verify session. Please refresh the page.</p>
          </div>
        </div>
      </div>
    );
  }

  const serverAuthenticated =
    data?.account_a?.is_authorized === true &&
    data?.account_b?.is_authorized === true;

  if (!serverAuthenticated) {
    return <Navigate to="/onboarding" replace />;
  }

  return <Outlet />;
}
