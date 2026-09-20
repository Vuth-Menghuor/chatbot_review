import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { useChatStore } from '~/stores/chat.store';
import {
  authFetchAuthed,
  clearLegacyStoredTokens,
  loginRequest,
  logoutRequest,
  refreshTokenRequest,
  registerRequest,
  updateMeRequest,
  type AuthUser,
  type LoginCredentials,
  type RegisterPayload,
  type UpdateProfilePayload,
} from '~/services/auth-api/authApi';

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null);
  const user = ref<AuthUser | null>(null);
  const initialized = ref(false);
  const loading = ref(false);

  const isAuthenticated = computed(() => Boolean(accessToken.value));

  function apiBaseUrl(): string {
    const runtimeConfig = useRuntimeConfig();
    return String(runtimeConfig.public.gdceApiBaseUrl ?? 'http://localhost:8000').replace(/\/+$/, '');
  }

  function applySession(tokens: { access_token: string }, nextUser: AuthUser) {
    accessToken.value = tokens.access_token;
    user.value = nextUser;
  }

  function clearSession() {
    accessToken.value = null;
    user.value = null;
  }

  async function refreshSession(): Promise<boolean> {
    try {
      const data = await refreshTokenRequest(apiBaseUrl());
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
    user.value = result.data;
    return result.data;
  }

  async function updateMe(payload: UpdateProfilePayload) {
    const token = await getValidAccessToken();
    if (!token) throw new Error('You must be logged in to update your profile.');

    const result = await updateMeRequest(apiBaseUrl(), token, payload);
    accessToken.value = result.accessToken;
    user.value = result.data;
    return result.data;
  }

  async function init() {
    if (initialized.value) return;
    loading.value = true;
    try {
      clearLegacyStoredTokens();
      await refreshSession();
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
    clearSession();
    // Chat content is only a temporary per-browser cache; never leave it for the next user.
    useChatStore().clearAll();
    if (!token) return;
    try {
      await logoutRequest(apiBaseUrl(), token);
    } catch {
      // Session is already cleared locally.
    }
  }

  /** Access tokens are memory-only; a page reload restores them through the refresh cookie. */
  async function getValidAccessToken(): Promise<string | null> {
    return accessToken.value;
  }

  return {
    accessToken,
    user,
    initialized,
    loading,
    isAuthenticated,
    init,
    login,
    register,
    logout,
    fetchMe,
    updateMe,
    refreshSession,
    getValidAccessToken,
    clearSession,
  };
});
