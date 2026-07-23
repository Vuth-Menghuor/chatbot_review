<script setup lang="ts">
import { computed } from 'vue';
import { useAppLocale } from '~/composables/common/useAppLocale';

const { locale, setLanguage } = useAppLocale();

const nextLanguage = computed(() => (locale.value === 'km' ? 'en' : 'km'));
const nextLanguageFlag = computed(() => (nextLanguage.value === 'km' ? '🇰🇭' : '🇺🇸'));
const nextLanguageLabel = computed(() => (nextLanguage.value === 'km' ? 'ខ្មែរ' : 'EN'));

function toggleLanguage() {
  setLanguage(nextLanguage.value);
}
</script>

<template>
  <BaseButton
    variant="text"
    custom-class="absolute left-4 top-4 z-20 inline-flex !h-9 !min-w-[78px] items-center justify-center gap-2 rounded-lg border border-white/30 bg-white/14 px-3 text-xs font-bold text-white shadow-[0_8px_20px_rgba(0,0,0,0.14)] backdrop-blur-md transition hover:border-white/45 hover:bg-white/20 focus:outline-none focus:ring-2 focus:ring-[#7bd7e8]/70 sm:left-6 sm:top-6"
    aria-label="Switch language"
    @click="toggleLanguage"
  >
    <span class="text-base leading-none" aria-hidden="true">{{ nextLanguageFlag }}</span>
    <span class="ml-2 leading-none">{{ nextLanguageLabel }}</span>
  </BaseButton>
</template>
