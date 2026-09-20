import { buildChatApiUrl, ChatApiRequestError } from '~/services/chat-api/chatApiHttp';

export interface AuthUser {
  id: string;
  full_name: string;
  nickname?: string | null;
  email: string;
  phone?: string | null;
  address?: string | null;
  avatar_url?: string | null;
  role: string;
  is_active: boolean;
}

export interface LoginCredentials { email: string; password: string; }
export interface RegisterPayload { full_name: string; email: string; password: string; }

// The long-lived refresh token is an HttpOnly cookie and is never exposed to JS.
export interface TokenResponse { access_token: string; token_type: string; user: AuthUser; }

export interface UpdateProfilePayload {
  full_name?: string;
  nickname?: string | null;
  email?: string;
  phone?: string | null;
  address?: string | null;
  avatar_url?: string | null;
}

/** Remove tokens left behind by pre-cookie versions of the frontend. */
export function clearLegacyStoredTokens(): void {
  if (typeof localStorage === 'undefined') return;
  localStorage.removeItem('gdce:access-token');
  localStorage.removeItem('gdce:refresh-token');
}

function parseApiError(body: string, status: number): string {
  try {
    const detail = (JSON.parse(body) as { detail?: unknown }).detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && typeof (detail[0] as { msg?: unknown })?.msg === 'string') {
      return (detail[0] as { msg: string }).msg;
    }
  } catch { /* use status fallback */ }
  if (status === 401) return 'Invalid email or password';
  if (status === 409) return 'Email is already registered';
  return 'Request failed. Please try again.';
}

async function authFetchJson<T>(
  baseUrl: string,
  path: string,
  options: { method?: string; body?: unknown; accessToken?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'application/json' };
  if (options.accessToken) headers.Authorization = `Bearer ${options.accessToken}`;
  const response = await fetch(buildChatApiUrl(baseUrl, path), {
    method: options.method ?? (options.body ? 'POST' : 'GET'),
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    credentials: 'include',
  });
  if (!response.ok) {
    const body = await response.text();
    throw new ChatApiRequestError(parseApiError(body, response.status), response.status, body);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function loginRequest(baseUrl: string, credentials: LoginCredentials): Promise<TokenResponse> {
  return authFetchJson<TokenResponse>(baseUrl, '/api/v1/auth/login', { body: credentials });
}

export function registerRequest(baseUrl: string, payload: RegisterPayload): Promise<AuthUser> {
  return authFetchJson<AuthUser>(baseUrl, '/api/v1/auth/register', { body: payload });
}

export function refreshTokenRequest(baseUrl: string): Promise<TokenResponse> {
  return authFetchJson<TokenResponse>(baseUrl, '/api/v1/auth/refresh', { method: 'POST' });
}

/** Cookie-backed refresh for callers that need to retry a single request. */
export async function tryRefreshSession(baseUrl: string): Promise<TokenResponse | null> {
  try {
    return await refreshTokenRequest(baseUrl);
  } catch {
    return null;
  }
}

export function logoutRequest(baseUrl: string, accessToken: string): Promise<void> {
  return authFetchJson(baseUrl, '/api/v1/auth/logout', { accessToken, body: {} });
}

export function updateMeRequest(baseUrl: string, accessToken: string, payload: UpdateProfilePayload) {
  return authFetchAuthed<AuthUser>(baseUrl, '/api/v1/auth/me', accessToken, { method: 'PATCH', body: payload });
}

/** Authenticated request with one 401 → cookie refresh → retry attempt. */
export async function authFetchAuthed<T>(
  baseUrl: string,
  path: string,
  accessToken: string,
  options: { method?: string; body?: unknown } = {},
): Promise<{ data: T; accessToken: string }> {
  try {
    return { data: await authFetchJson<T>(baseUrl, path, { ...options, accessToken }), accessToken };
  } catch (err) {
    if (!(err instanceof ChatApiRequestError) || err.status !== 401) throw err;
    const refreshed = await refreshTokenRequest(baseUrl);
    return {
      data: await authFetchJson<T>(baseUrl, path, { ...options, accessToken: refreshed.access_token }),
      accessToken: refreshed.access_token,
    };
  }
}
