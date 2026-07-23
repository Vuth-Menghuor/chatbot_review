<script setup lang="ts">
import { useAppLocale } from '~/composables/common/useAppLocale';

const { t } = useAppLocale();
</script>

<template>
  <BaseButton
    type="button"
    block
    variant="text"
    size="large"
    :tooltip="t('auth.login.googleSoonTitle')"
    custom-class="!mt-6 !min-h-[44px] rounded-full border border-white/16 bg-black/18 text-sm font-semibold text-white/86 hover:border-white/28 hover:bg-black/24"
  >
    <span class="inline-flex items-center justify-center gap-3">
      <AuthGoogleIcon class="h-4 w-4 shrink-0" />
      <span>{{ t('auth.login.continueWithGoogle') }}</span>
    </span>
  </BaseButton>
</template>
