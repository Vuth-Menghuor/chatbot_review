<script setup lang="ts">
import { ref } from 'vue';
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
const error = ref('');

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
    error.value =
      err instanceof ChatApiRequestError
        ? err.message || t('auth.register.failed')
        : t('auth.register.failed');
  }
}
</script>

<template>
  <AuthSplitLayout>
    <AuthFormHeader :title="t('auth.register.title')" :subtitle="t('auth.register.subtitle')" />

    <form class="mt-10 space-y-3 text-left" @submit.prevent="onSubmit">
      <AuthField
        v-model="fullName"
        autocomplete="name"
        :label="t('auth.register.fullName')"
        :placeholder="t('auth.register.fullNamePlaceholder')"
      />

      <AuthField
        v-model="email"
        type="email"
        autocomplete="email"
        :label="t('auth.login.email')"
        :placeholder="t('auth.login.emailPlaceholder')"
      />

      <AuthField
        v-model="password"
        password
        autocomplete="new-password"
        :label="t('auth.login.password')"
        :placeholder="t('auth.register.passwordPlaceholder')"
      />

      <p
        v-if="error"
        class="rounded-sm border border-[#e46161]/35 bg-[#e76666]/10 px-3 py-2 text-center text-base font-medium text-[#ffb6b6]"
      >
        {{ error }}
      </p>

      <AuthGoogleComingSoonButton />

      <BaseButton
        type="submit"
        block
        size="large"
        custom-class="!mx-auto !mt-12 !flex !min-h-[50px] !w-[340px] !rounded-full bg-[#e76666] text-sm font-bold uppercase tracking-normal text-white hover:bg-[#f07a7a]"
        :loading="authStore.loading"
      >
        {{ t('auth.register.submit') }}
      </BaseButton>
    </form>

    <p class="mt-8 text-center text-base text-white/70">
      {{ t('auth.register.haveAccount') }}
      <BaseButton
        variant="text"
        custom-class="inline h-auto min-h-0 min-w-0 px-1 py-0 font-bold text-white normal-case hover:underline"
        @click="navigateTo('/login')"
      >
        {{ t('auth.register.signInLink') }}
      </BaseButton>
    </p>
  </AuthSplitLayout>
</template>
