<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { definePageMeta, navigateTo, useRoute } from '#imports';
import { ChatApiRequestError } from '~/services/chat-api';
import { useAuthStore } from '~/stores/auth.store';
import { useUserStore } from '~/stores/user.store';
import { useAppLocale } from '~/composables/common/useAppLocale';

definePageMeta({ layout: 'auth' });

const route = useRoute();
const authStore = useAuthStore();
const userStore = useUserStore();
const { t } = useAppLocale();

const email = ref('');
const password = ref('');
const error = ref('');

const registrationSuccess = computed(() => route.query.registered === '1');

onMounted(() => {
  const queryEmail = route.query.email;
  if (typeof queryEmail === 'string') {
    email.value = queryEmail.trim();
  }
});

async function onSubmit() {
  error.value = '';

  const trimmedEmail = email.value.trim();
  if (!trimmedEmail || !password.value) {
    error.value = t('auth.login.requiredFields');
    return;
  }

  try {
    await authStore.login({ email: trimmedEmail, password: password.value });
    userStore.syncFromAuthUser();

    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    await navigateTo(redirect || '/');
  } catch (err) {
    error.value =
      err instanceof ChatApiRequestError
        ? err.message || t('auth.login.failed')
        : t('auth.login.failed');
  }
}
</script>

<template>
  <AuthSplitLayout>
    <AuthFormHeader :title="t('auth.login.title')" :subtitle="t('auth.login.subtitle')" />

    <p
      v-if="registrationSuccess"
      class="mt-8 rounded-sm border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-medium text-emerald-200"
    >
      {{ t('auth.register.success') }}
    </p>

    <form class="mt-10 space-y-3 text-left" @submit.prevent="onSubmit">
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
        autocomplete="current-password"
        :label="t('auth.login.password')"
        :placeholder="t('auth.login.passwordPlaceholder')"
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
        {{ t('auth.login.submit') }}
      </BaseButton>
    </form>

    <p class="mt-8 text-center text-base text-white/70">
      {{ t('auth.login.noAccount') }}
      <BaseButton
        variant="text"
        custom-class="inline h-auto min-h-0 min-w-0 px-1 py-0 font-bold text-white normal-case hover:underline"
        @click="navigateTo('/register')"
      >
        {{ t('auth.login.registerLink') }}
      </BaseButton>
    </p>
  </AuthSplitLayout>
</template>
