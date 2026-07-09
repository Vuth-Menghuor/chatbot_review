<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { EyeIcon, EyeOffIcon } from 'lucide-vue-next';
import { definePageMeta, navigateTo } from '#imports';
import { ChatApiRequestError } from '~/services/chat-api';
import { useAuthStore } from '~/stores/auth.store';
import { useAppLocale } from '~/composables/common/useAppLocale';

definePageMeta({ layout: 'auth' });

const authStore = useAuthStore();
const { t } = useAppLocale();

const fullName = ref('');
const email = ref('');
const password = ref('');
const showPassword = ref(false);
const error = ref('');
const termsAccepted = ref(false);
const termsDialogOpen = ref(false);
const termsTouched = ref(false);

const nameError = computed(() => {
  if (!error.value) return '';
  if (error.value.toLowerCase().includes('name')) return error.value;
  return '';
});

const emailError = computed(() => {
  if (!error.value) return '';
  if (error.value.toLowerCase().includes('email')) return error.value;
  return '';
});

const passwordError = computed(() => {
  if (!error.value || nameError.value || emailError.value) return '';
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

async function onSubmit() {
  error.value = '';
  const trimmedName = fullName.value.trim();
  const trimmedEmail = email.value.trim();

  if (!trimmedName || !trimmedEmail || !password.value) {
    error.value = t('auth.register.requiredFields');
    return;
  }
  if (password.value.length < 8) {
    error.value = t('auth.register.passwordMin');
    return;
  }
  if (!ensureTermsAccepted()) return;

  try {
    await authStore.register({
      full_name: trimmedName,
      email: trimmedEmail,
      password: password.value,
    });
    await navigateTo({
      path: '/login',
      query: { email: trimmedEmail, registered: '1' },
    });
  } catch (err) {
    if (err instanceof ChatApiRequestError) {
      error.value = err.message || t('auth.register.failed');
      return;
    }
    error.value = t('auth.register.failed');
  }
}
</script>

<template>
  <div class="flex min-h-screen flex-col">
    <div class="flex flex-1 flex-col items-center justify-center px-4 py-8">
      <div class="w-full max-w-[420px]">
        <AuthLogo class="mb-6" />

        <div
          class="overflow-hidden rounded-sm border border-[#b8c9d3]/60 bg-[#dce8ee] shadow-2xl shadow-black/20"
        >
          <div class="h-[4px] w-full bg-[#1b5875]" aria-hidden="true" />

          <div class="px-8 pb-6 pt-8">
            <div class="mb-5 text-center">
              <h1 class="text-2xl font-bold leading-tight text-[#1b5875]">
                {{ t('auth.register.title') }}
              </h1>
            </div>

            <form class="flex flex-col gap-3.5" @submit.prevent="onSubmit">
              <div class="flex flex-col gap-3">
                <BaseInput
                  v-model="fullName"
                  type="text"
                  variant="auth"
                  autocomplete="name"
                  :label="t('auth.register.fullName')"
                  :placeholder="t('auth.register.fullNamePlaceholder')"
                  :error="nameError"
                />

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
                  autocomplete="new-password"
                  :label="t('auth.login.password')"
                  :placeholder="t('auth.register.passwordPlaceholder')"
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
                v-if="error && !nameError && !emailError && !passwordError && !termsError"
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
                {{ t('auth.register.submit') }}
              </BaseButton>

              <p class="text-center text-sm leading-relaxed text-[#5f6f78]">
                {{ t('auth.register.haveAccount') }}
                <BaseButton
                  variant="text"
                  custom-class="inline h-auto min-h-0 min-w-0 px-1 py-0 text-md font-bold text-[#1b5875] normal-case hover:underline"
                  @click="navigateTo('/login')"
                >
                  {{ t('auth.register.signInLink') }}
                </BaseButton>
              </p>
            </form>
          </div>
        </div>
      </div>
    </div>

    <footer class="shrink-0 px-4 pb-6 text-center">
      <p class="text-md leading-relaxed font-medium text-white/95">
        {{ t('auth.login.footer') }}
      </p>
      <p class="mt-1 text-sm leading-relaxed text-white/75">
        {{ t('auth.login.copyright') }}
      </p>
    </footer>
  </div>
</template>
