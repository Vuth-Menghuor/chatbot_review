import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import {
  authFetchAuthed,
  clearStoredTokens,
  getStoredAccessToken,
  getStoredRefreshToken,
  loginRequest,
  logoutRequest,
  refreshTokenRequest,
  registerRequest,
  setStoredTokens,
  type AuthUser,
  type LoginCredentials,
  type RegisterPayload,
} from '~/services/auth-api/authApi';

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null);
  const refreshToken = ref<string | null>(null);
  const user = ref<AuthUser | null>(null);
  const initialized = ref(false);
  const loading = ref(false);

  const isAuthenticated = computed(() => Boolean(accessToken.value));

  function apiBaseUrl(): string {
    const runtimeConfig = useRuntimeConfig();
    return String(runtimeConfig.public.gdceApiBaseUrl ?? 'http://localhost:8000').replace(/\/+$/, '');
  }

  function hydrateFromStorage() {
    accessToken.value = getStoredAccessToken();
    refreshToken.value = getStoredRefreshToken();
  }

  function applySession(tokens: { access_token: string; refresh_token: string }, nextUser: AuthUser) {
    accessToken.value = tokens.access_token;
    refreshToken.value = tokens.refresh_token;
    user.value = nextUser;
    setStoredTokens(tokens.access_token, tokens.refresh_token);
  }

  function clearSession() {
    accessToken.value = null;
    refreshToken.value = null;
    user.value = null;
    clearStoredTokens();
  }

  async function refreshSession(): Promise<boolean> {
    const storedRefresh = refreshToken.value ?? getStoredRefreshToken();
    if (!storedRefresh) {
      clearSession();
      return false;
    }

    try {
      const data = await refreshTokenRequest(apiBaseUrl(), storedRefresh);
      applySession(data, data.user);
      return true;
    } catch {
      clearSession();
      return false;
    }
  }

  async function fetchMe() {
    if (!accessToken.value) return null;

    const result = await authFetchAuthed<AuthUser>(
      apiBaseUrl(),
      '/api/v1/auth/me',
      accessToken.value,
    );
    accessToken.value = result.accessToken;
    refreshToken.value = result.refreshToken;
    user.value = result.data;
    return result.data;
  }

  async function init() {
    if (initialized.value) return;
    loading.value = true;
    hydrateFromStorage();

    try {
      if (accessToken.value) {
        try {
          await fetchMe();
        } catch {
          clearSession();
        }
      }
    } finally {
      initialized.value = true;
      loading.value = false;
    }
  }

  async function login(credentials: LoginCredentials) {
    loading.value = true;
    try {
      const data = await loginRequest(apiBaseUrl(), credentials);
      applySession(data, data.user);
      initialized.value = true;
      return data.user;
    } finally {
      loading.value = false;
    }
  }

  async function register(payload: RegisterPayload) {
    loading.value = true;
    try {
      return await registerRequest(apiBaseUrl(), payload);
    } finally {
      loading.value = false;
    }
  }

  async function logout() {
    const token = accessToken.value;
    const storedRefresh = refreshToken.value;
    clearSession();
    if (!token) return;
    try {
      await logoutRequest(apiBaseUrl(), token, storedRefresh);
    } catch {
      // Session is already cleared locally.
    }
  }

  /** Returns the current access token, hydrating from storage when needed. */
  async function getValidAccessToken(): Promise<string | null> {
    if (!accessToken.value) {
      hydrateFromStorage();
    }
    return accessToken.value;
  }

  return {
    accessToken,
    refreshToken,
    user,
    initialized,
    loading,
    isAuthenticated,
    init,
    login,
    register,
    logout,
    fetchMe,
    refreshSession,
    getValidAccessToken,
    clearSession,
  };
});
