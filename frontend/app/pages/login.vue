<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { EyeIcon, EyeOffIcon } from 'lucide-vue-next';
import { definePageMeta, navigateTo, useRoute } from '#imports';
import { ChatApiRequestError } from '~/services/chat-api';
import { useAuthStore } from '~/stores/auth.store';
import { useUserStore } from '~/stores/user.store';
import { useNotificationStore } from '~/stores/notification.store';
import { useAppLocale } from '~/composables/common/useAppLocale';
import GoogleIcon from '~/components/auth/GoogleIcon.vue';

definePageMeta({ layout: 'auth' });

const route = useRoute();
const authStore = useAuthStore();
const userStore = useUserStore();
const notificationStore = useNotificationStore();
const { t } = useAppLocale();

const email = ref('');
const password = ref('');
const showPassword = ref(false);
const error = ref('');
const termsAccepted = ref(false);
const termsDialogOpen = ref(false);
const termsTouched = ref(false);

const registrationSuccess = computed(() => route.query.registered === '1');

onMounted(() => {
  const queryEmail = route.query.email;
  if (typeof queryEmail === 'string' && queryEmail.trim()) {
    email.value = queryEmail.trim();
  }
});

const emailError = computed(() => {
  if (!error.value) return '';
  if (error.value.toLowerCase().includes('email')) return error.value;
  return '';
});

const passwordError = computed(() => {
  if (!error.value || emailError.value) return '';
  if (error.value === t('auth.login.termsRequired')) return '';
  return '';
});

const termsError = computed(() => {
  if (!termsTouched.value) return '';
  if (error.value === t('auth.login.termsRequired')) return error.value;
  return '';
});

watch(termsAccepted, (value) => {
  if (value && error.value === t('auth.login.termsRequired')) {
    error.value = '';
    termsTouched.value = false;
  }
});

function ensureTermsAccepted(): boolean {
  termsTouched.value = true;
  if (termsAccepted.value) return true;
  error.value = t('auth.login.termsRequired');
  return false;
}

function onForgotPassword() {
  notificationStore.showToast({
    type: 'info',
    title: t('auth.login.forgotPasswordSoonTitle'),
    message: t('auth.login.forgotPasswordSoonMessage'),
  });
}

function onGoogleSignIn() {
  if (!ensureTermsAccepted()) return;

  notificationStore.showToast({
    type: 'info',
    title: t('auth.login.googleSoonTitle'),
    message: t('auth.login.googleSoonMessage'),
  });
}

async function onSubmit() {
  error.value = '';
  const trimmedEmail = email.value.trim();
  if (!trimmedEmail || !password.value) {
    error.value = t('auth.login.requiredFields');
    return;
  }
  if (!ensureTermsAccepted()) return;

  try {
    await authStore.login({ email: trimmedEmail, password: password.value });
    userStore.syncFromAuthUser();
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await navigateTo(redirect || '/');
  } catch (err) {
    if (err instanceof ChatApiRequestError) {
      error.value = err.message || t('auth.login.failed');
      return;
    }
    error.value = t('auth.login.failed');
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <div class="flex flex-1 flex-col items-center justify-center px-4 py-6">
      <div class="w-full max-w-[420px]">
        <AuthLogo class="mb-5" />

        <div
          class="overflow-hidden rounded-sm border border-[#b8c9d3]/60 bg-[#dce8ee] shadow-2xl shadow-black/20"
        >
          <div class="h-[4px] w-full bg-[#1b5875]" aria-hidden="true" />

          <div class="px-8 pb-6 pt-8">
            <div class="mb-5 text-center">
              <h1 class="text-2xl font-bold leading-tight text-[#1b5875]">
                {{ t('auth.login.title') }}
              </h1>
            </div>

            <p
              v-if="registrationSuccess"
              class="mb-4 rounded-sm bg-green-50 px-3 py-2 text-center text-sm font-medium text-green-700"
              role="status"
            >
              {{ t('auth.register.success') }}
            </p>

            <form class="flex flex-col gap-3.5" @submit.prevent="onSubmit">
              <div class="flex flex-col gap-3">
                <BaseInput
                  v-model="email"
                  type="email"
                  variant="auth"
                  autocomplete="email"
                  :label="t('auth.login.email')"
                  :placeholder="t('auth.login.emailPlaceholder')"
                  :error="emailError"
                />

                <BaseInput
                  v-model="password"
                  :type="showPassword ? 'text' : 'password'"
                  variant="auth"
                  autocomplete="current-password"
                  :label="t('auth.login.password')"
                  :placeholder="t('auth.login.passwordPlaceholder')"
                  :append-icon="showPassword ? EyeOffIcon : EyeIcon"
                  :error="passwordError"
                  @append-click="showPassword = !showPassword"
                />
              </div>

              <AuthTermsAcceptance
                v-model="termsAccepted"
                v-model:dialog-open="termsDialogOpen"
                :error="termsError"
                compact
                small
              />

              <p
                v-if="error && !emailError && !passwordError && !termsError"
                class="rounded-sm bg-red-50 px-3 py-2 text-center text-sm font-medium text-red-600"
              >
                {{ error }}
              </p>

              <BaseButton
                type="submit"
                color="primary"
                block
                size="large"
                custom-class="!min-h-[46px] !rounded-sm font-bold tracking-tight normal-case shadow-md"
                :loading="authStore.loading"
              >
                {{ t('auth.login.submit') }}
              </BaseButton>

              <div class="flex items-center gap-3 py-0.5">
                <div class="h-px flex-1 bg-[#b8c5ce]" />
                <span class="text-[11px] font-bold uppercase tracking-wide text-[#6b7c86]">
                  {{ t('auth.login.orDivider') }}
                </span>
                <div class="h-px flex-1 bg-[#b8c5ce]" />
              </div>

              <BaseButton
                variant="outlined"
                block
                size="large"
                custom-class="!min-h-[44px] !rounded-sm border-[#b8c5ce] bg-white font-bold tracking-tight normal-case text-[#1a1a1a] hover:bg-[#f3f7f9]"
                :prepend-icon="GoogleIcon"
                @click="onGoogleSignIn"
              >
                {{ t('auth.login.continueWithGoogle') }}
              </BaseButton>

              <p class="text-center text-xs text-[#5f6f78]">
                {{ t('auth.login.noAccount') }}
                <BaseButton
                  variant="text"
                  custom-class="inline h-auto min-h-0 min-w-0 px-1 py-0 text-md font-bold text-[#1b5875] normal-case hover:underline"
                  @click="navigateTo('/register')"
                >
                  {{ t('auth.login.registerLink') }}
                </BaseButton>
              </p>
            </form>
          </div>

          <div class="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 border-t border-[#c5d5de] bg-white px-8 py-4">
            <BaseButton
              variant="text"
              custom-class="h-auto min-w-0 px-0 py-0 text-sm font-semibold text-[#1b5875] normal-case hover:underline"
              @click="onForgotPassword"
            >
              {{ t('auth.login.forgotPassword') }}
            </BaseButton>
          </div>
        </div>
      </div>
    </div>

    <footer class="shrink-0 px-4 pb-8 text-center">
      <p class="text-md leading-relaxed font-medium text-white/95">
        {{ t('auth.login.footer') }}
      </p>
      <p class="mt-1 text-xs text-white/75">
        {{ t('auth.login.copyright') }}
      </p>
    </footer>
  </div>
</template>
