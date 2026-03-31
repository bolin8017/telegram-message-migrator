export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
    public readonly waitSeconds?: number,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

const UNAUTHENTICATED_ENDPOINTS = ['/api/auth/status', '/api/setup/mode'];

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({
      detail: response.statusText,
    }));

    if (response.status === 401 && !UNAUTHENTICATED_ENDPOINTS.includes(path)) {
      window.location.href = '/onboarding';
    }

    throw new ApiError(
      response.status,
      body.detail ?? 'Unknown error',
      body.wait_seconds,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
