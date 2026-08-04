import { buildChatApiUrl, ChatApiRequestError } from '~/services/chat-api/chatApiHttp';

export const ACCESS_TOKEN_KEY = 'gdce:access-token';
export const REFRESH_TOKEN_KEY = 'gdce:refresh-token';

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

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: AuthUser;
}

export interface UpdateProfilePayload {
  full_name?: string;
  nickname?: string | null;
  email?: string;
  phone?: string | null;
  address?: string | null;
  avatar_url?: string | null;
}

export function getStoredAccessToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setStoredTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearStoredTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

function parseApiError(body: string, status: number): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    const detail = parsed.detail;
    if (typeof detail === 'string' && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length) {
      const first = detail[0] as { msg?: string };
      if (typeof first?.msg === 'string') return first.msg;
    }
  } catch {
    // fall through
  }
  if (status === 401) return 'Invalid email or password';
  if (status === 409) return 'Email is already registered';
  return 'Request failed. Please try again.';
}

async function authFetchJson<T>(
  baseUrl: string,
  path: string,
  options: { method?: string; body?: unknown; accessToken?: string } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  };
  if (options.accessToken) headers.Authorization = `Bearer ${options.accessToken}`;

  const response = await fetch(buildChatApiUrl(baseUrl, path), {
    method: options.method ?? (options.body ? 'POST' : 'GET'),
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new ChatApiRequestError(parseApiError(body, response.status), response.status, body);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function loginRequest(
  baseUrl: string,
  credentials: LoginCredentials,
): Promise<TokenResponse> {
  return authFetchJson<TokenResponse>(baseUrl, '/api/v1/auth/login', { body: credentials });
}

export async function registerRequest(
  baseUrl: string,
  payload: RegisterPayload,
): Promise<AuthUser> {
  return authFetchJson<AuthUser>(baseUrl, '/api/v1/auth/register', { body: payload });
}

export async function refreshTokenRequest(
  baseUrl: string,
  refreshToken: string,
): Promise<TokenResponse> {
  return authFetchJson<TokenResponse>(baseUrl, '/api/v1/auth/refresh', {
    body: { refresh_token: refreshToken },
  });
}

export async function logoutRequest(
  baseUrl: string,
  accessToken: string,
  refreshToken?: string | null,
): Promise<void> {
  await authFetchJson(baseUrl, '/api/v1/auth/logout', {
    accessToken,
    body: refreshToken ? { refresh_token: refreshToken } : {},
  });
}

export async function fetchMeRequest(baseUrl: string, accessToken: string): Promise<AuthUser> {
  return authFetchJson<AuthUser>(baseUrl, '/api/v1/auth/me', { accessToken });
}

export async function updateMeRequest(
  baseUrl: string,
  accessToken: string,
  payload: UpdateProfilePayload,
): Promise<{ data: AuthUser; accessToken: string; refreshToken: string | null }> {
  return authFetchAuthed<AuthUser>(baseUrl, '/api/v1/auth/me', accessToken, {
    method: 'PATCH',
    body: payload,
  });
}

export async function tryRefreshAccessToken(baseUrl: string): Promise<string | null> {
  const data = await tryRefreshSession(baseUrl);
  return data?.access_token ?? null;
}

/** Refresh JWT pair from storage; returns null and clears tokens on failure. */
export async function tryRefreshSession(baseUrl: string): Promise<TokenResponse | null> {
  const refreshToken = getStoredRefreshToken();
  if (!refreshToken) return null;
  try {
    const data = await refreshTokenRequest(baseUrl, refreshToken);
    setStoredTokens(data.access_token, data.refresh_token);
    return data;
  } catch {
    clearStoredTokens();
    return null;
  }
}

/** Authenticated JSON request with one 401 → refresh → retry attempt. */
export async function authFetchAuthed<T>(
  baseUrl: string,
  path: string,
  accessToken: string,
  options: { method?: string; body?: unknown } = {},
): Promise<{ data: T; accessToken: string; refreshToken: string | null }> {
  try {
    const data = await authFetchJson<T>(baseUrl, path, {
      ...options,
      accessToken,
    });
    return {
      data,
      accessToken,
      refreshToken: getStoredRefreshToken(),
    };
  } catch (err) {
    if (!(err instanceof ChatApiRequestError) || err.status !== 401) throw err;

    const refreshed = await tryRefreshSession(baseUrl);
    if (!refreshed) throw err;

    const data = await authFetchJson<T>(baseUrl, path, {
      ...options,
      accessToken: refreshed.access_token,
    });
    return {
      data,
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token,
    };
  }
}
