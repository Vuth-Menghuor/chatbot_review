<template>
  <NuxtRouteAnnouncer />
  <v-app>
    <NuxtLayout>
      <NuxtPage />
    </NuxtLayout>
  </v-app>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { storeToRefs } from 'pinia';
import { useAppLocale } from '~/composables/common/useAppLocale';
import { usePreferencesStore, type FontSizePreference } from '~/stores/preferences.store';

const { locale } = useAppLocale();
const preferencesStore = usePreferencesStore();
const { fontSize } = storeToRefs(preferencesStore);

const FONT_SIZE_CLASSES = ['font-size-small', 'font-size-medium', 'font-size-large'] as const;

function applyFontSize(size: FontSizePreference) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  FONT_SIZE_CLASSES.forEach((className) => root.classList.remove(className));
  root.classList.add(`font-size-${size}`);
}

// Connect Pinia theme ↔ Vuetify (must run in setup, not in a Nuxt plugin).
useAppTheme();

onMounted(() => {
  preferencesStore.init();
  applyFontSize(fontSize.value);
});

watch(fontSize, applyFontSize);

useHead(() => ({
  htmlAttrs: {
    lang: locale.value,
  },
  title: 'អគ្គនាយកដ្ឋានគយនិងរដ្ឋាករកម្ពុជា',
  link: [{ rel: 'icon', type: 'image/png', href: '/logo/gdce-new-seal.png' }],
}));
</script>
